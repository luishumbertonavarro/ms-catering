"""
MOCK — solo para desarrollo y tests.
Devuelve datos falsos pero deterministas (derivados del UUID del paciente).
Reemplazar por una implementación HTTP real cuando se integre el ms-pacientes.
"""
from uuid import UUID

from catering.domain.gateways.paciente_gateway import DatosPacienteExterno, PacienteGateway


class PacienteGatewayMock(PacienteGateway):
    async def obtener_datos(self, paciente_id: UUID) -> DatosPacienteExterno:
        # ID abreviado como código, para que sea determinista y trazable en logs.
        codigo = str(paciente_id)[:8].upper()
        return DatosPacienteExterno(
            nombre=f"Paciente Mock {codigo}",
            codigo=codigo,
            numero_identificacion=f"00000000{codigo[:4]}",
        )
