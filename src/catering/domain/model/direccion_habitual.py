from dataclasses import dataclass
from uuid import UUID, uuid4

from catering.domain.model.value_objects import DireccionEntrega


@dataclass
class DireccionHabitual:
    id: UUID
    calendario_id: UUID
    paciente_id: UUID
    nombre: str
    direccion: DireccionEntrega
    es_principal: bool = False

    @classmethod
    def crear(
        cls,
        calendario_id: UUID,
        paciente_id: UUID,
        nombre: str,
        direccion: DireccionEntrega,
        es_principal: bool = False,
    ) -> "DireccionHabitual":
        return cls(
            id=uuid4(),
            calendario_id=calendario_id,
            paciente_id=paciente_id,
            nombre=nombre,
            direccion=direccion,
            es_principal=es_principal,
        )
