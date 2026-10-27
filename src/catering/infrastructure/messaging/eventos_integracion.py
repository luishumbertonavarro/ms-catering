"""Traduce eventos de dominio de CalendarioEntrega a mensajes de integración.

Contratos: Eventos_Integracion_NUR-TRICENTER.docx, sección 4. Convención del grupo:
exchange topic `nurtricenter.events`, routing key `entidad.participio` en minúsculas,
el payload viaja directo (sin sobre).
"""
from dataclasses import dataclass
from datetime import datetime

from catering.domain.model import CalendarioEntrega, DireccionEntrega
from catering.domain.model.eventos import (
    CalendarioEntregaCancelado,
    CalendarioEntregaCompletado,
    CalendarioEntregaCreado,
    DiaSinEntregaMarcado,
    DireccionEntregaCambiada,
    EventoDominio,
)


@dataclass(frozen=True)
class MensajeIntegracion:
    tipo: str
    routing_key: str
    payload: dict
    ocurrido_en: datetime


def _direccion(d: DireccionEntrega) -> dict:
    return {
        "direccion": d.direccion,
        "referencia": d.referencia,
        "zona": d.zona,
        "latitud": float(d.latitud) if d.latitud is not None else None,
        "longitud": float(d.longitud) if d.longitud is not None else None,
    }


def _id(valor) -> str | None:
    return str(valor) if valor is not None else None


def a_mensaje(evento: EventoDominio, calendario: CalendarioEntrega) -> MensajeIntegracion:
    base = {"calendario_id": str(calendario.id), "paciente_id": str(calendario.paciente_id)}
    match evento:
        case CalendarioEntregaCreado(direccion_entrega=direccion):
            tipo, routing_key = "CalendarioEntregaCreado", "calendario.creado"
            payload = base | {
                "plan_nutricional_id": _id(calendario.plan_nutricional_id),
                "fecha_inicio": calendario.fecha_inicio.isoformat(),
                "fecha_fin": calendario.fecha_fin.isoformat(),
                "total_dias": calendario.total_dias,
                "direccion_entrega": _direccion(direccion),
            }
        case DireccionEntregaCambiada():
            tipo, routing_key = "DireccionEntregaCambiada", "direccion_entrega.cambiada"
            payload = {
                "calendario_id": str(calendario.id),
                "entrega_id": str(evento.entrega_id),
                "paciente_id": str(calendario.paciente_id),
                "fecha_entrega": evento.fecha_entrega.isoformat(),
                "origen": evento.origen,
                "nombre_direccion_habitual": evento.nombre_direccion_habitual,
                "direccion_anterior": _direccion(evento.direccion_anterior),
                "direccion_nueva": _direccion(evento.direccion_nueva),
            }
        case DiaSinEntregaMarcado():
            tipo, routing_key = "DiaSinEntregaMarcado", "dia_sin_entrega.marcado"
            payload = {
                "calendario_id": str(calendario.id),
                "entrega_id": str(evento.entrega_id),
                "paciente_id": str(calendario.paciente_id),
                "fecha_entrega": evento.fecha_entrega.isoformat(),
                "motivo": evento.motivo,
            }
        case CalendarioEntregaCancelado(fechas_canceladas=fechas):
            tipo, routing_key = "CalendarioEntregaCancelado", "calendario.cancelado"
            payload = base | {"fechas_canceladas": [f.isoformat() for f in fechas]}
        case CalendarioEntregaCompletado():
            tipo, routing_key = "CalendarioEntregaCompletado", "calendario.completado"
            payload = base | {
                "fecha_fin": evento.fecha_fin.isoformat(),
                "entregas_realizadas": evento.entregas_realizadas,
                "dias_sin_entrega": evento.dias_sin_entrega,
            }
        case _:
            raise ValueError(f"Evento sin contrato de integración: {type(evento).__name__}")
    return MensajeIntegracion(tipo, routing_key, payload, evento.ocurrido_en)
