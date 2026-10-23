"""App de verificación del provider `ms-catering`.

Envuelve la app **real** (`presentation/api/main.app`, sin tocarla) y le añade dos
cosas que solo existen durante la verificación de Pact:

1. **Una transacción externa que se revierte al apagar el servidor.** Se abre una
   única conexión; las sesiones de la app se crean sobre ella con
   `join_transaction_mode="create_savepoint"`, igual que la fixture `cliente` de
   `tests/integration/conftest.py`. Al terminar, `rollback()`: la base de
   desarrollo queda intacta.

2. **La ruta `POST /_pact/provider-states`.** El verificador de Pact la llama antes
   (`setup`) y después (`teardown`) de cada interacción. En el `setup` se abre un
   SAVEPOINT y se preparan los datos del estado; en el `teardown` se revierte ese
   SAVEPOINT. Así cada interacción empieza desde cero, aunque dos de ellas usen el
   mismo `calendario_id`.

La ruta de estados corre en el mismo event loop que las peticiones de la app. Por
eso ambas pueden compartir la conexión de asyncpg sin problemas de hilos.
"""
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import date, timedelta
from uuid import UUID

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from catering.domain.model import (
    CalendarioEntrega,
    DireccionEntrega,
    Entrega,
    EstadoCalendario,
)
from catering.infrastructure.persistence import CalendarioEntregaRepositoryImpl, get_db_session
from catering.presentation.api.main import app as app_real

RUTA_ESTADOS = "/_pact/provider-states"


class CambioDeEstado(BaseModel):
    """Cuerpo que envía el verificador de Pact a la ruta de estados."""

    state: str
    action: str = "setup"
    params: dict = {}


# ---------------------------------------------------------------------------
# Handlers de provider states — uno por cada `given(...)` de los pacts
# ---------------------------------------------------------------------------

async def _existe_un_calendario_activo(session: AsyncSession, params: dict) -> None:
    """Crea un calendario ACTIVO de 15 días (2099) con una dirección habitual.

    Se construye por el constructor (rehidratación) porque el contrato fija el
    `calendario_id`, y la factoría `crear()` siempre genera uno nuevo.
    """
    calendario_id = UUID(params["calendario_id"])
    plan_id = UUID("66666666-6666-4666-8666-666666666666")
    inicio = date(2099, 1, 1)
    domicilio = DireccionEntrega("Av. Banzer 123", referencia="Portón verde", zona="Equipetrol")
    calendario = CalendarioEntrega(
        id=calendario_id,
        paciente_id=UUID(params["paciente_id"]),
        fecha_inicio=inicio,
        fecha_fin=date(2099, 1, 15),
        estado=EstadoCalendario.ACTIVO,
        entregas=[
            Entrega.crear(calendario_id, inicio + timedelta(days=d), domicilio, plan_id)
            for d in range(15)
        ],
        direcciones_habituales=[],
        dias_sin_entrega=[],
        plan_nutricional_id=plan_id,
    )
    calendario.registrar_direccion_habitual(
        "trabajo",
        DireccionEntrega("Calle Libertad 456", referencia="Oficina 3B", zona="Centro"),
        es_principal=True,
    )
    await CalendarioEntregaRepositoryImpl(session).guardar(calendario)


async def _no_existe_el_calendario(session: AsyncSession, params: dict) -> None:
    """Garantiza la precondición en vez de suponerla."""
    if await CalendarioEntregaRepositoryImpl(session).obtener_por_id(UUID(params["calendario_id"])):
        raise RuntimeError(
            f"El calendario {params['calendario_id']} existe y el estado exige que no exista."
        )


HANDLERS: dict[str, Callable[[AsyncSession, dict], Awaitable[None]]] = {
    "existe un calendario activo": _existe_un_calendario_activo,
    "no existe el calendario": _no_existe_el_calendario,
}


# ---------------------------------------------------------------------------
# Composición de la app de verificación
# ---------------------------------------------------------------------------

def crear_app_provider(url_bd: str) -> FastAPI:
    contexto: dict = {}
    savepoints: list = []

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        motor = create_async_engine(url_bd, poolclass=NullPool)
        conexion: AsyncConnection = await motor.connect()
        transaccion = await conexion.begin()
        fabrica = async_sessionmaker(
            bind=conexion,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )

        async def _sesion_de_verificacion() -> AsyncGenerator[AsyncSession, None]:
            async with fabrica() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        contexto.update(conexion=conexion, fabrica=fabrica)
        app_real.dependency_overrides[get_db_session] = _sesion_de_verificacion
        try:
            yield
        finally:
            app_real.dependency_overrides.clear()
            await transaccion.rollback()
            await conexion.close()
            await motor.dispose()

    provider = FastAPI(lifespan=lifespan)

    @provider.post(RUTA_ESTADOS)
    async def cambiar_estado(cambio: CambioDeEstado) -> dict:
        if cambio.action == "teardown":
            if savepoints:
                await savepoints.pop().rollback()
            return {}

        handler = HANDLERS.get(cambio.state)
        if handler is None:
            raise HTTPException(status_code=400, detail=f"Provider state sin handler: '{cambio.state}'")

        savepoints.append(await contexto["conexion"].begin_nested())
        async with contexto["fabrica"]() as session:
            await handler(session, cambio.params)
            await session.commit()
        return {}

    # La ruta de estados se registra antes del mount para que tenga prioridad.
    provider.mount("/", app_real)
    return provider
