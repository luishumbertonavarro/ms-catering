from datetime import date

from catering.domain.model.value_objects import AnticipacionMinima


class ValidadorCambioCalendarioService:
    """Domain service to check whether a modification is allowed on a given delivery date."""

    def __init__(self) -> None:
        self._anticipacion = AnticipacionMinima()

    def puede_modificar(self, fecha_entrega: date, fecha_solicitud: date) -> bool:
        return self._anticipacion.es_valida(fecha_entrega, fecha_solicitud)

    def dias_restantes_para_modificar(self, fecha_entrega: date, fecha_solicitud: date) -> int:
        delta = (fecha_entrega - fecha_solicitud).days
        return max(0, self._anticipacion.DIAS_REQUERIDOS - delta)
