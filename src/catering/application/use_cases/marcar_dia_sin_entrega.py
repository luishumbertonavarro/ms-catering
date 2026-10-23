from catering.application.commands import MarcarDiaSinEntregaCommand
from catering.domain.exceptions import CalendarioNoEncontradoError
from catering.domain.repositories import CalendarioEntregaRepository


class MarcarDiaSinEntregaUseCase:
    def __init__(self, repo: CalendarioEntregaRepository) -> None:
        self._repo = repo

    async def ejecutar(self, cmd: MarcarDiaSinEntregaCommand) -> None:
        calendario = await self._repo.obtener_por_id(cmd.calendario_id)
        if calendario is None:
            raise CalendarioNoEncontradoError(cmd.calendario_id)

        calendario.marcar_dia_sin_entrega(
            fecha=cmd.fecha,
            fecha_solicitud=cmd.fecha_solicitud,
            motivo=cmd.motivo,
        )
        await self._repo.guardar(calendario)
