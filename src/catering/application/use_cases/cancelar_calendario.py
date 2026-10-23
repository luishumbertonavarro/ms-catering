from catering.application.commands import CancelarCalendarioCommand
from catering.domain.exceptions import CalendarioNoEncontradoError
from catering.domain.repositories import CalendarioEntregaRepository


class CancelarCalendarioUseCase:
    def __init__(self, repo: CalendarioEntregaRepository) -> None:
        self._repo = repo

    async def ejecutar(self, cmd: CancelarCalendarioCommand) -> None:
        calendario = await self._repo.obtener_por_id(cmd.calendario_id)
        if calendario is None:
            raise CalendarioNoEncontradoError(cmd.calendario_id)

        calendario.cancelar_calendario()
        await self._repo.guardar(calendario)
