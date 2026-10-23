from datetime import date

from catering.application.queries import (
    ListarCalendariosActivosQuery,
    ObtenerCalendarioPacienteQuery,
    ObtenerCalendarioPorIdQuery,
    ObtenerEntregasDeFechaQuery,
    VerificarPuedeModificarQuery,
)
from catering.domain.model import CalendarioEntrega
from catering.domain.repositories import CalendarioEntregaRepository
from catering.domain.services import ValidadorCambioCalendarioService


class ObtenerCalendarioPorIdHandler:
    def __init__(self, repo: CalendarioEntregaRepository) -> None:
        self._repo = repo

    async def ejecutar(self, query: ObtenerCalendarioPorIdQuery) -> CalendarioEntrega | None:
        return await self._repo.obtener_por_id(query.calendario_id)


class ObtenerCalendarioPacienteHandler:
    def __init__(self, repo: CalendarioEntregaRepository) -> None:
        self._repo = repo

    async def ejecutar(self, query: ObtenerCalendarioPacienteQuery) -> CalendarioEntrega | None:
        return await self._repo.obtener_por_paciente(query.paciente_id)


class ListarCalendariosActivosHandler:
    def __init__(self, repo: CalendarioEntregaRepository) -> None:
        self._repo = repo

    async def ejecutar(self, query: ListarCalendariosActivosQuery) -> list[CalendarioEntrega]:
        return await self._repo.listar_activos()


class ObtenerEntregasDeFechaHandler:
    def __init__(self, repo: CalendarioEntregaRepository) -> None:
        self._repo = repo

    async def ejecutar(self, query: ObtenerEntregasDeFechaQuery) -> list[CalendarioEntrega]:
        return await self._repo.listar_con_entregas_en_fecha(query.fecha)


class VerificarPuedeModificarHandler:
    def __init__(self, servicio: ValidadorCambioCalendarioService) -> None:
        self._servicio = servicio

    async def ejecutar(self, query: VerificarPuedeModificarQuery) -> dict:
        puede = self._servicio.puede_modificar(query.fecha_entrega, query.fecha_solicitud)
        dias_faltantes = self._servicio.dias_restantes_para_modificar(
            query.fecha_entrega, query.fecha_solicitud
        )
        return {"puede_modificar": puede, "dias_faltantes": dias_faltantes}
