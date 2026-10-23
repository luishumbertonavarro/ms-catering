from dataclasses import dataclass
from datetime import date
from uuid import UUID


@dataclass(frozen=True)
class ObtenerCalendarioPorIdQuery:
    calendario_id: UUID


@dataclass(frozen=True)
class ObtenerCalendarioPacienteQuery:
    paciente_id: UUID


@dataclass(frozen=True)
class ListarCalendariosActivosQuery:
    pass


@dataclass(frozen=True)
class ObtenerEntregasDeFechaQuery:
    fecha: date


@dataclass(frozen=True)
class VerificarPuedeModificarQuery:
    fecha_entrega: date
    fecha_solicitud: date
