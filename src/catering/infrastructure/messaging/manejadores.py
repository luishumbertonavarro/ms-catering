"""Reacciones de BC4 a los eventos de otros microservicios (ver docx, sección 5.2).

- servicio.contratado (CATERING): crea el calendario de entregas del período contratado.
- contrato.cancelado (CATERING) / plan_nutricional.cancelado: cancela el calendario activo.
- contrato.completado (CATERING) / plan_nutricional.finalizado: completa el calendario activo.
- plan_nutricional.creado: vincula el plan al calendario activo del paciente.

Cada reacción trabaja contra el puerto del dominio y pasa por el agregado, así que también
genera sus propios eventos (p. ej. calendario.cancelado) vía outbox, en la misma transacción.
"""
import logging
from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from catering.domain.model import CalendarioEntrega, DireccionEntrega
from catering.domain.repositories import CalendarioEntregaRepository
from catering.infrastructure.messaging.consumidor import Manejador, campo
from catering.infrastructure.persistence.calendario_repository_impl import (
    CalendarioEntregaRepositoryImpl,
)

logger = logging.getLogger(__name__)

Reaccion = Callable[[CalendarioEntregaRepository, dict], Awaitable[None]]

_CATERING = "CATERING"
# El contrato no trae dirección: el calendario nace con una provisional que el paciente cambia.
DIRECCION_PROVISIONAL = DireccionEntrega(
    direccion="Por definir",
    referencia="El paciente define la dirección desde su calendario",
)


def _es_catering(payload: dict) -> bool:
    # Los eventos de plan no traen tipo de servicio: aplican siempre.
    tipo = payload.get("tipoServicio", payload.get("tipo_servicio", _CATERING))
    return tipo == _CATERING


def _paciente_id(payload: dict) -> UUID:
    return UUID(str(campo(payload, "pacienteId", "paciente_id")))


async def _calendario_activo(
    repo: CalendarioEntregaRepository, payload: dict
) -> CalendarioEntrega | None:
    calendario = await repo.obtener_por_paciente(_paciente_id(payload))
    if calendario is None:
        logger.info("Paciente %s sin calendario activo; nada que hacer", _paciente_id(payload))
    return calendario


async def servicio_contratado(repo: CalendarioEntregaRepository, payload: dict) -> None:
    if not _es_catering(payload):
        return
    existente = await _calendario_activo(repo, payload)
    if existente is not None:
        logger.info("El paciente ya tiene el calendario activo %s; no se crea otro", existente.id)
        return
    fecha_inicio = date.fromisoformat(str(campo(payload, "fechaInicio", "fecha_inicio"))[:10])
    duracion = int(campo(payload, "duracionDias", "duracion_dias"))
    calendario = CalendarioEntrega.crear(
        paciente_id=_paciente_id(payload),
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_inicio + timedelta(days=duracion - 1),
        direccion_default=DIRECCION_PROVISIONAL,
    )
    await repo.guardar(calendario)
    logger.info("Calendario %s creado por contrato de catering", calendario.id)


async def plan_nutricional_creado(repo: CalendarioEntregaRepository, payload: dict) -> None:
    calendario = await _calendario_activo(repo, payload)
    if calendario is None:
        return
    calendario.vincular_plan_nutricional(UUID(str(campo(payload, "plan_id", "planId"))))
    await repo.guardar(calendario)


async def cancelar_calendario(repo: CalendarioEntregaRepository, payload: dict) -> None:
    if not _es_catering(payload):
        return
    calendario = await _calendario_activo(repo, payload)
    if calendario is None:
        return
    calendario.cancelar_calendario()
    await repo.guardar(calendario)


async def completar_calendario(repo: CalendarioEntregaRepository, payload: dict) -> None:
    if not _es_catering(payload):
        return
    calendario = await _calendario_activo(repo, payload)
    if calendario is None:
        return
    calendario.completar_calendario()
    await repo.guardar(calendario)


REACCIONES: dict[str, Reaccion] = {
    "servicio.contratado": servicio_contratado,
    "contrato.cancelado": cancelar_calendario,
    "contrato.completado": completar_calendario,
    "plan_nutricional.creado": plan_nutricional_creado,
    "plan_nutricional.cancelado": cancelar_calendario,
    "plan_nutricional.finalizado": completar_calendario,
}


def _con_repositorio(reaccion: Reaccion) -> Manejador:
    """Adapta una reacción al consumidor: el repositorio usa la sesión de la transacción del mensaje."""

    async def manejador(session: AsyncSession, payload: dict) -> None:
        await reaccion(CalendarioEntregaRepositoryImpl(session), payload)

    return manejador


MANEJADORES: dict[str, Manejador] = {rk: _con_repositorio(r) for rk, r in REACCIONES.items()}
