from dataclasses import dataclass, field
from datetime import date
from uuid import UUID, uuid4

from catering.domain.model.enums import EstadoEntrega
from catering.domain.model.value_objects import DireccionEntrega, Etiqueta


@dataclass
class Entrega:
    id: UUID
    calendario_id: UUID
    fecha: date
    estado: EstadoEntrega
    direccion: DireccionEntrega
    plan_nutricional_id: UUID | None = None
    etiqueta: Etiqueta | None = None

    @classmethod
    def crear(
        cls,
        calendario_id: UUID,
        fecha: date,
        direccion: DireccionEntrega,
        plan_nutricional_id: UUID | None = None,
    ) -> "Entrega":
        return cls(
            id=uuid4(),
            calendario_id=calendario_id,
            fecha=fecha,
            estado=EstadoEntrega.PROGRAMADA,
            direccion=direccion,
            plan_nutricional_id=plan_nutricional_id,
        )

    def cambiar_direccion(self, nueva_direccion: DireccionEntrega) -> None:
        self.direccion = nueva_direccion

    def marcar_sin_entrega(self) -> None:
        self.estado = EstadoEntrega.SIN_ENTREGA

    def cancelar(self) -> None:
        self.estado = EstadoEntrega.CANCELADA

    def registrar_entrega(self) -> None:
        self.estado = EstadoEntrega.ENTREGADA

    @property
    def es_modificable(self) -> bool:
        return self.estado == EstadoEntrega.PROGRAMADA

    @property
    def tiene_etiqueta(self) -> bool:
        return self.etiqueta is not None
