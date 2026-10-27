import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from catering.domain.exceptions import (
    AnticipacionInsuficienteError,
    CalendarioInactivoError,
    CalendarioNoEncontradoError,
    DireccionHabitualDuplicadaError,
    EntregaNoEncontradaError,
    EntregaNoModificableError,
    FechaFueraDeRangoError,
    PacienteNoEncontradoError,
)
from catering.infrastructure.config import settings
from catering.presentation.api.security import proteger

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("ms-catering iniciando (env=%s)", settings.app_env)
    # Import diferido: la app (y sus tests) se construyen sin tocar broker ni Consul.
    from catering.infrastructure.persistence.database import AsyncSessionFactory

    procesos = []
    registro = None
    if settings.rabbitmq_url:
        from catering.infrastructure.messaging.consumidor import ConsumidorEventos
        from catering.infrastructure.messaging.manejadores import MANEJADORES
        from catering.infrastructure.messaging.outbox_relay import OutboxRelay

        procesos = [
            OutboxRelay(
                AsyncSessionFactory,
                settings.rabbitmq_url,
                settings.rabbitmq_exchange,
                settings.outbox_intervalo_segundos,
            ),
            ConsumidorEventos(
                AsyncSessionFactory,
                settings.rabbitmq_url,
                settings.rabbitmq_exchange,
                settings.rabbitmq_cola,
                MANEJADORES,
            ),
        ]
    if settings.consul_url:
        from catering.infrastructure.discovery.consul import RegistroConsul

        registro = RegistroConsul(
            settings.consul_url, settings.servicio_nombre, settings.servicio_puerto
        )
        registro.iniciar()
    for proceso in procesos:
        proceso.iniciar()
    yield
    for proceso in procesos:
        await proceso.detener()
    if registro is not None:
        await registro.desregistrar()
    logger.info("ms-catering detenido")


app = FastAPI(
    title="ms-catering — NUR-TRICENTER",
    version="0.2.0",
    lifespan=lifespan,
)

# ── Exception handlers ─────────────────────────────────────────────────────────

@app.exception_handler(AnticipacionInsuficienteError)
async def anticipacion_handler(request: Request, exc: AnticipacionInsuficienteError):
    return JSONResponse(
        status_code=422,
        content={"detail": str(exc), "tipo": "ANTICIPACION_INSUFICIENTE"},
    )


@app.exception_handler(EntregaNoEncontradaError)
async def entrega_no_encontrada_handler(request: Request, exc: EntregaNoEncontradaError):
    return JSONResponse(
        status_code=404,
        content={"detail": str(exc), "tipo": "ENTREGA_NO_ENCONTRADA"},
    )


@app.exception_handler(EntregaNoModificableError)
async def entrega_no_modificable_handler(request: Request, exc: EntregaNoModificableError):
    return JSONResponse(
        status_code=409,
        content={"detail": str(exc), "tipo": "ENTREGA_NO_MODIFICABLE"},
    )


@app.exception_handler(CalendarioInactivoError)
async def calendario_inactivo_handler(request: Request, exc: CalendarioInactivoError):
    return JSONResponse(
        status_code=409,
        content={"detail": str(exc), "tipo": "CALENDARIO_INACTIVO"},
    )


@app.exception_handler(DireccionHabitualDuplicadaError)
async def direccion_duplicada_handler(request: Request, exc: DireccionHabitualDuplicadaError):
    return JSONResponse(
        status_code=409,
        content={"detail": str(exc), "tipo": "DIRECCION_HABITUAL_DUPLICADA"},
    )


@app.exception_handler(FechaFueraDeRangoError)
async def fecha_fuera_rango_handler(request: Request, exc: FechaFueraDeRangoError):
    return JSONResponse(
        status_code=422,
        content={"detail": str(exc), "tipo": "FECHA_FUERA_DE_RANGO"},
    )


@app.exception_handler(CalendarioNoEncontradoError)
async def calendario_no_encontrado_handler(request: Request, exc: CalendarioNoEncontradoError):
    return JSONResponse(
        status_code=404,
        content={"detail": str(exc), "tipo": "CALENDARIO_NO_ENCONTRADO"},
    )


@app.exception_handler(PacienteNoEncontradoError)
async def paciente_no_encontrado_handler(request: Request, exc: PacienteNoEncontradoError):
    return JSONResponse(
        status_code=404,
        content={"detail": str(exc), "tipo": "PACIENTE_NO_ENCONTRADO"},
    )


# ── Routers ────────────────────────────────────────────────────────────────────

from catering.presentation.api.routers.calendarios import router as calendarios_router  # noqa: E402
from catering.presentation.api.routers.health import router as health_router  # noqa: E402

# Roles (claim `rol` del JWT): el paciente gestiona su calendario; los listados globales,
# crear y cancelar calendarios son de admin (ver dependencias por endpoint en el router).
app.include_router(health_router)
app.include_router(
    calendarios_router,
    dependencies=[
        Depends(proteger(lectura=("admin", "paciente", "nutricionista"), escritura=("admin", "paciente")))
    ],
)
