from dataclasses import dataclass, field
from datetime import date
from uuid import UUID


@dataclass(frozen=True)
class DireccionData:
    direccion: str
    referencia: str | None = None
    zona: str | None = None


@dataclass(frozen=True)
class CrearCalendarioCommand:
    paciente_id: UUID
    fecha_inicio: date
    fecha_fin: date
    direccion_inicial: DireccionData
    plan_nutricional_id: UUID | None = None


@dataclass(frozen=True)
class CambiarDireccionEntregaCommand:
    calendario_id: UUID
    fecha_entrega: date
    nueva_direccion: DireccionData
    fecha_solicitud: date


@dataclass(frozen=True)
class MarcarDiaSinEntregaCommand:
    calendario_id: UUID
    fecha: date
    fecha_solicitud: date
    motivo: str | None = None


@dataclass(frozen=True)
class RegistrarDireccionHabitualCommand:
    calendario_id: UUID
    nombre: str
    direccion: DireccionData
    es_principal: bool = False


@dataclass(frozen=True)
class AsignarDireccionHabitualADiaCommand:
    calendario_id: UUID
    fecha_entrega: date
    nombre_direccion: str
    fecha_solicitud: date


@dataclass(frozen=True)
class CancelarCalendarioCommand:
    calendario_id: UUID
