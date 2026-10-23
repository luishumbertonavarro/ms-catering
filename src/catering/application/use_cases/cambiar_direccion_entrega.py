from catering.application.commands import CambiarDireccionEntregaCommand
from catering.domain.exceptions import CalendarioNoEncontradoError
from catering.domain.model import DireccionEntrega
from catering.domain.repositories import CalendarioEntregaRepository


class CambiarDireccionEntregaUseCase:
    def __init__(self, repo: CalendarioEntregaRepository) -> None:
        self._repo = repo

    async def ejecutar(self, cmd: CambiarDireccionEntregaCommand) -> None:
        calendario = await self._repo.obtener_por_id(cmd.calendario_id)
        if calendario is None:
            raise CalendarioNoEncontradoError(cmd.calendario_id)

        nueva_dir = DireccionEntrega(
            direccion=cmd.nueva_direccion.direccion,
            referencia=cmd.nueva_direccion.referencia,
            zona=cmd.nueva_direccion.zona,
        )
        calendario.cambiar_direccion_entrega(
            fecha=cmd.fecha_entrega,
            nueva_direccion=nueva_dir,
            fecha_solicitud=cmd.fecha_solicitud,
        )
        await self._repo.guardar(calendario)
