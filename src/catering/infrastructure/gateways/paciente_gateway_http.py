"""
Adaptador HTTP real hacia ms-pacientes.

En la relación de contrato, ms-catering es el **consumer** y ms-pacientes el
**provider**. El contrato que este adaptador espera está descrito en
`tests/contract/consumer/test_catering_consume_pacientes.py` y generado en
`pacts/ms-catering-ms-pacientes.json`.

Sus datos alimentan la `Etiqueta` de cada paquete (nombre, código e
identificación del paciente).
"""
from uuid import UUID

import httpx

from catering.domain.exceptions import PacienteNoEncontradoError
from catering.domain.gateways.paciente_gateway import DatosPacienteExterno, PacienteGateway


class PacienteGatewayHttp(PacienteGateway):
    def __init__(self, base_url: str, timeout: float = 5.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def obtener_datos(self, paciente_id: UUID) -> DatosPacienteExterno:
        async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
            respuesta = await client.get(
                f"/pacientes/{paciente_id}", headers={"Accept": "application/json"}
            )
        if respuesta.status_code == 404:
            raise PacienteNoEncontradoError(paciente_id)
        respuesta.raise_for_status()
        cuerpo = respuesta.json()
        return DatosPacienteExterno(
            nombre=cuerpo["nombre"],
            codigo=cuerpo["codigo"],
            numero_identificacion=cuerpo["numero_identificacion"],
        )
