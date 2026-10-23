from catering.application.commands import CrearCalendarioCommand
from catering.domain.model import CalendarioEntrega, DireccionEntrega
from catering.domain.repositories import CalendarioEntregaRepository


class CrearCalendarioUseCase:
    def __init__(self, repo: CalendarioEntregaRepository) -> None:
        self._repo = repo

    async def ejecutar(self, cmd: CrearCalendarioCommand) -> CalendarioEntrega:
        direccion = DireccionEntrega(
            direccion=cmd.direccion_inicial.direccion,
            referencia=cmd.direccion_inicial.referencia,
            zona=cmd.direccion_inicial.zona,
        )
        calendario = CalendarioEntrega.crear(
            paciente_id=cmd.paciente_id,
            fecha_inicio=cmd.fecha_inicio,
            fecha_fin=cmd.fecha_fin,
            direccion_default=direccion,
            plan_nutricional_id=cmd.plan_nutricional_id,
        )
        await self._repo.guardar(calendario)
        return calendario
