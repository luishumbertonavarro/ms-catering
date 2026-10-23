from datetime import date
from uuid import UUID

from pydantic import BaseModel


# ---- Shared ----

class DireccionRequest(BaseModel):
    direccion: str
    referencia: str | None = None
    zona: str | None = None


# ---- Calendarios ----

class CrearCalendarioRequest(BaseModel):
    paciente_id: UUID
    fecha_inicio: date
    fecha_fin: date
    direccion_inicial: DireccionRequest
    plan_nutricional_id: UUID | None = None


class EntregaResponse(BaseModel):
    id: UUID
    fecha: date
    estado: str
    direccion: str
    referencia: str | None
    zona: str | None
    tiene_etiqueta: bool


class DireccionHabitualResponse(BaseModel):
    id: UUID
    nombre: str
    direccion: str
    referencia: str | None
    zona: str | None
    es_principal: bool


class CalendarioResponse(BaseModel):
    id: UUID
    paciente_id: UUID
    fecha_inicio: date
    fecha_fin: date
    estado: str
    total_dias: int
    plan_nutricional_id: UUID | None
    entregas: list[EntregaResponse]
    direcciones_habituales: list[DireccionHabitualResponse]


# ---- Entregas ----

class CambiarDireccionRequest(BaseModel):
    nueva_direccion: DireccionRequest


class MarcarSinEntregaRequest(BaseModel):
    motivo: str | None = None


class AsignarDireccionHabitualRequest(BaseModel):
    nombre_direccion: str


# ---- Direcciones habituales ----

class RegistrarDireccionHabitualRequest(BaseModel):
    nombre: str
    direccion: DireccionRequest
    es_principal: bool = False


# ---- Verificación ----

class VerificarModificacionResponse(BaseModel):
    puede_modificar: bool
    dias_faltantes: int
