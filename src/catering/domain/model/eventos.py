from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from uuid import UUID

from catering.domain.model.value_objects import DireccionEntrega


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class EventoDominio:
    """Hecho ya ocurrido en el calendario. Se publica vía outbox al guardar el agregado."""

    calendario_id: UUID
    ocurrido_en: datetime = field(default_factory=_ahora, kw_only=True)


@dataclass(frozen=True)
class CalendarioEntregaCreado(EventoDominio):
    direccion_entrega: DireccionEntrega


@dataclass(frozen=True)
class DireccionEntregaCambiada(EventoDominio):
    entrega_id: UUID
    fecha_entrega: date
    origen: str  # MANUAL | DIRECCION_HABITUAL
    nombre_direccion_habitual: str | None
    direccion_anterior: DireccionEntrega
    direccion_nueva: DireccionEntrega


@dataclass(frozen=True)
class DiaSinEntregaMarcado(EventoDominio):
    entrega_id: UUID
    fecha_entrega: date
    motivo: str | None


@dataclass(frozen=True)
class CalendarioEntregaCancelado(EventoDominio):
    fechas_canceladas: tuple[date, ...]


@dataclass(frozen=True)
class CalendarioEntregaCompletado(EventoDominio):
    fecha_fin: date
    entregas_realizadas: int
    dias_sin_entrega: int
