"""Fixtures de las pruebas de integración.

A diferencia de las pruebas unitarias (`tests/conftest.py`), aquí **no hay ningún
mock**: cada test recorre el camino completo

    HTTP → router → caso de uso → repositorio SQLAlchemy → PostgreSQL → HTTP

Tres decisiones sostienen este módulo:

1. **Una sola base de datos, y no se ensucia.** Se usa la misma `db_catering`
   del docker-compose, sin crear ninguna base aparte. Cada test corre dentro de
   una transacción que se **revierte al terminar**, así que al acabar la suite la
   base queda exactamente como estaba: cero filas nuevas. Ver `cliente` para el
   detalle de cómo se consigue.

2. **Un solo punto de inyección.** El router define su `_get_repo`, que depende
   de la hoja compartida `get_db_session`. Sobrescribir esa única dependencia
   redirige toda la aplicación a la conexión de prueba.

3. **La suite no se rompe sin Docker.** Si el servidor PostgreSQL no responde, o
   responde pero sin las migraciones aplicadas, `comprobar_bd` hace
   `pytest.skip` y las pruebas unitarias siguen corriendo.
"""

import asyncio
import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from catering.infrastructure.config.settings import settings
from catering.infrastructure.persistence import get_db_session
from catering.presentation.api.main import app


# ---------------------------------------------------------------------------
# Disponibilidad de la base (se comprueba una sola vez por sesión de pytest)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def url_bd() -> str:
    """URL de la base contra la que se integran las pruebas.

    Es la misma de desarrollo, la que levanta el docker-compose. Se puede apuntar
    a otra con la variable de entorno `TEST_DATABASE_URL`.
    """
    return os.getenv("TEST_DATABASE_URL") or settings.database_url


async def _hay_conexion(url: str) -> None:
    """Abre una conexión y lee la tabla raíz; propaga el error si algo falta.

    Consultar `calendarios_entrega` (y no solo `SELECT 1`) distingue "PostgreSQL
    arriba y migrado" de "PostgreSQL arriba pero vacío": el esquema lo crea
    Alembic, no el docker-compose.
    """
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1 FROM calendarios_entrega LIMIT 1"))
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def comprobar_bd(url_bd: str) -> str:
    """Salta las pruebas de integración si no hay PostgreSQL levantado y migrado.

    Es una fixture síncrona que abre su propio bucle con `asyncio.run`: así no
    depende del bucle de pytest-asyncio, que en este proyecto tiene alcance de
    función y no sobreviviría a una fixture de sesión.
    """
    try:
        asyncio.run(_hay_conexion(url_bd))
    except Exception as exc:  # noqa: BLE001 — cualquier fallo aquí es "no disponible"
        pytest.skip(
            "PostgreSQL no está disponible o no tiene el esquema; se omiten las "
            "pruebas de integración. Levántalo con: "
            "docker compose up -d catering_db && uv run alembic upgrade head "
            f"({type(exc).__name__}: {exc})"
        )
    return url_bd


# ---------------------------------------------------------------------------
# Motor y cliente HTTP (uno por test)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def motor_test(comprobar_bd: str):
    """Motor asíncrono propio de las pruebas.

    Deliberadamente **no** se reutiliza el `engine` de
    `infrastructure/persistence/database.py`: ese lo comparte la aplicación y
    tiene su propio pool. `NullPool` evita además que queden conexiones abiertas
    de un test a otro, ya que cada test corre en su propio bucle de eventos.
    """
    engine = create_async_engine(comprobar_bd, poolclass=NullPool, future=True)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def cliente(motor_test) -> AsyncGenerator[AsyncClient, None]:
    """Cliente HTTP contra la app FastAPI real, dentro de una transacción reversible.

    Este es el corazón del aislamiento, y merece explicarse porque no es obvio.

    El problema: la aplicación hace `commit()` al final de cada petición. Si ese
    commit llegara a la base, cada test dejaría basura en `db_catering`.

    La solución, en tres pasos:

    1. Se abre **una** conexión y se inicia en ella una transacción externa.
    2. Las sesiones que usa la app se crean sobre esa misma conexión con
       `join_transaction_mode="create_savepoint"`. Así, el `commit()` de cada
       petición no confirma nada de verdad: solo libera un SAVEPOINT dentro de la
       transacción externa, que sigue abierta.
    3. Al acabar el test se hace `rollback()` de la transacción externa. Todo lo
       que escribieron las peticiones desaparece de golpe.

    Dos consecuencias importantes:

    - Las peticiones **sí se ven entre sí** (comparten transacción), que es justo
      lo que necesita un flujo end-to-end para ser realista.
    - El `rollback()` de una petición fallida revierte solo hasta su SAVEPOINT,
      no lo anterior — exactamente el comportamiento de producción. Por eso los
      tests del flujo incorrecto pueden comprobar que un error no borró lo que ya
      estaba guardado.

    Como nada se confirma, no hace falta `TRUNCATE` entre tests ni una base de
    datos aparte: la base de desarrollo queda intacta.
    """
    conexion = await motor_test.connect()
    transaccion = await conexion.begin()

    fabrica_sesion = async_sessionmaker(
        bind=conexion,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )

    async def _sesion_de_test() -> AsyncGenerator[AsyncSession, None]:
        # Mismo contrato que el `get_db_session` de producción: commit al salir,
        # rollback ante cualquier excepción. Aquí ambos operan sobre el SAVEPOINT.
        async with fabrica_sesion() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db_session] = _sesion_de_test
    try:
        # `ASGITransport` habla con la app en el mismo proceso: no hace falta
        # levantar uvicorn, pero sí se ejercitan el router, `Depends`, la
        # validación de Pydantic y los manejadores de excepciones.
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        await transaccion.rollback()
        await conexion.close()
