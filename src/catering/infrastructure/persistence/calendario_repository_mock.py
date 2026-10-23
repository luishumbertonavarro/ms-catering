"""
MOCK — repositorio en memoria para desarrollo sin base de datos.
Reemplazar por CalendarioEntregaRepositoryImpl cuando la BD esté disponible.
"""
from datetime import date
from uuid import UUID

from catering.domain.model.calendario_entrega import CalendarioEntrega
from catering.domain.repositories.calendario_repository import CalendarioEntregaRepository
from catering.domain.model.enums import EstadoCalendario, EstadoEntrega


_store: dict[UUID, CalendarioEntrega] = {}


class InMemoryCalendarioRepository(CalendarioEntregaRepository):

    async def guardar(self, calendario: CalendarioEntrega) -> None:
        _store[calendario.id] = calendario

    async def obtener_por_id(self, id: UUID) -> CalendarioEntrega | None:
        return _store.get(id)

    async def obtener_por_paciente(self, paciente_id: UUID) -> CalendarioEntrega | None:
        return next(
            (
                c for c in _store.values()
                if c.paciente_id == paciente_id and c.estado == EstadoCalendario.ACTIVO
            ),
            None,
        )

    async def listar_con_entregas_en_fecha(self, fecha: date) -> list[CalendarioEntrega]:
        return [
            c for c in _store.values()
            if any(e.fecha == fecha and e.estado == EstadoEntrega.PROGRAMADA for e in c.entregas)
        ]

    async def listar_activos(self) -> list[CalendarioEntrega]:
        return [c for c in _store.values() if c.estado == EstadoCalendario.ACTIVO]
