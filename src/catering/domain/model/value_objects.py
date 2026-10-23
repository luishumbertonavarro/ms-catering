from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class DireccionEntrega:
    direccion: str
    referencia: str | None = None
    zona: str | None = None
    latitud: Decimal | None = None
    longitud: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.direccion or not self.direccion.strip():
            raise ValueError("La dirección no puede estar vacía")


@dataclass(frozen=True)
class AnticipacionMinima:
    DIAS_REQUERIDOS: int = 2

    def es_valida(self, fecha_entrega: date, fecha_solicitud: date) -> bool:
        delta = (fecha_entrega - fecha_solicitud).days
        return delta >= self.DIAS_REQUERIDOS


@dataclass(frozen=True)
class Etiqueta:
    nombre_paciente: str
    codigo_paciente: str
    direccion_entrega: str
    fecha_entrega: date
    numero_identificacion: str


@dataclass(frozen=True)
class DiaSinEntrega:
    fecha: date
    motivo: str | None = None
