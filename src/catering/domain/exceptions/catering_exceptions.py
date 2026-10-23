from datetime import date
from uuid import UUID


class CateringDomainError(Exception):
    pass


class AnticipacionInsuficienteError(CateringDomainError):
    def __init__(self, fecha_entrega: date, fecha_solicitud: date, dias_requeridos: int = 2):
        super().__init__(
            f"Se requieren al menos {dias_requeridos} días de anticipación. "
            f"Fecha solicitada: {fecha_entrega}, fecha de solicitud: {fecha_solicitud}."
        )


class EntregaNoEncontradaError(CateringDomainError):
    def __init__(self, fecha: date):
        super().__init__(f"No existe una entrega programada para la fecha {fecha}.")


class EntregaNoModificableError(CateringDomainError):
    def __init__(self, fecha: date, estado: str):
        super().__init__(
            f"La entrega del {fecha} no puede modificarse porque su estado es '{estado}'."
        )


class CalendarioInactivoError(CateringDomainError):
    def __init__(self, estado: str):
        super().__init__(f"El calendario no está activo (estado actual: '{estado}').")


class DireccionHabitualDuplicadaError(CateringDomainError):
    def __init__(self, nombre: str):
        super().__init__(f"Ya existe una dirección habitual con el nombre '{nombre}'.")


class FechaFueraDeRangoError(CateringDomainError):
    def __init__(self, fecha: date, fecha_inicio: date, fecha_fin: date):
        super().__init__(
            f"La fecha {fecha} está fuera del rango del calendario "
            f"({fecha_inicio} – {fecha_fin})."
        )


class CalendarioNoEncontradoError(CateringDomainError):
    def __init__(self, id: UUID):
        super().__init__(f"No se encontró un calendario con id '{id}'.")


class DireccionHabitualNoEncontradaError(CateringDomainError):
    def __init__(self, nombre: str):
        super().__init__(f"No existe una dirección habitual con el nombre '{nombre}'.")


class PacienteNoEncontradoError(CateringDomainError):
    """El BC de Pacientes no reconoce al paciente (respuesta 404 de ms-pacientes)."""

    def __init__(self, paciente_id: UUID):
        super().__init__(f"No se encontró un paciente con id '{paciente_id}' en ms-pacientes.")
