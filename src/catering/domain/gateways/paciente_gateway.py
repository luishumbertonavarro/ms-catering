from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class DatosPacienteExterno:
    """DTO con los datos del paciente que pertenecen al BC de Pacientes (contexto externo).
    Se usan únicamente para enriquecer la Etiqueta de entrega.
    """
    nombre: str
    codigo: str
    numero_identificacion: str


class PacienteGateway(ABC):
    """Puerto (interfaz) hacia el microservicio de Pacientes.
    El dominio solo conoce esta abstracción; la implementación concreta vive en infraestructura.
    """

    @abstractmethod
    async def obtener_datos(self, paciente_id: UUID) -> DatosPacienteExterno: ...
