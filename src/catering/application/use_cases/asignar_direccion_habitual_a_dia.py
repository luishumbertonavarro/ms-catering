from catering.application.commands import AsignarDireccionHabitualADiaCommand
from catering.domain.exceptions import CalendarioNoEncontradoError
from catering.domain.repositories import CalendarioEntregaRepository


class AsignarDireccionHabitualADiaUseCase:
    def __init__(self, repo: CalendarioEntregaRepository) -> None:
        self._repo = repo

    async def ejecutar(self, cmd: AsignarDireccionHabitualADiaCommand) -> None:
        calendario = await self._repo.obtener_por_id(cmd.calendario_id)
        if calendario is None:
            raise CalendarioNoEncontradoError(cmd.calendario_id)

        calendario.asignar_direccion_habitual_a_dia(
            fecha=cmd.fecha_entrega,
            nombre_direccion=cmd.nombre_direccion,
            fecha_solicitud=cmd.fecha_solicitud,
        )
        await self._repo.guardar(calendario)
