from catering.application.commands import RegistrarDireccionHabitualCommand
from catering.domain.exceptions import CalendarioNoEncontradoError
from catering.domain.model import DireccionEntrega
from catering.domain.repositories import CalendarioEntregaRepository


class RegistrarDireccionHabitualUseCase:
    def __init__(self, repo: CalendarioEntregaRepository) -> None:
        self._repo = repo

    async def ejecutar(self, cmd: RegistrarDireccionHabitualCommand) -> None:
        calendario = await self._repo.obtener_por_id(cmd.calendario_id)
        if calendario is None:
            raise CalendarioNoEncontradoError(cmd.calendario_id)

        direccion = DireccionEntrega(
            direccion=cmd.direccion.direccion,
            referencia=cmd.direccion.referencia,
            zona=cmd.direccion.zona,
        )
        calendario.registrar_direccion_habitual(
            nombre=cmd.nombre,
            direccion=direccion,
            es_principal=cmd.es_principal,
        )
        await self._repo.guardar(calendario)
