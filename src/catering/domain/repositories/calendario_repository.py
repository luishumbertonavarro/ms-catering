from abc import ABC, abstractmethod
from datetime import date
from uuid import UUID

from catering.domain.model.calendario_entrega import CalendarioEntrega


class CalendarioEntregaRepository(ABC):

    @abstractmethod
    async def guardar(self, calendario: CalendarioEntrega) -> None: ...

    @abstractmethod
    async def obtener_por_id(self, id: UUID) -> CalendarioEntrega | None: ...

    @abstractmethod
    async def obtener_por_paciente(self, paciente_id: UUID) -> CalendarioEntrega | None: ...

    @abstractmethod
    async def listar_con_entregas_en_fecha(self, fecha: date) -> list[CalendarioEntrega]: ...

    @abstractmethod
    async def listar_activos(self) -> list[CalendarioEntrega]: ...
