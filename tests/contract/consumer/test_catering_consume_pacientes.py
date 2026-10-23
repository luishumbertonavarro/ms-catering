"""Contrato consumer: `ms-catering` → `ms-pacientes`.

Aquí ms-catering es el **consumer**: el adaptador real `PacienteGatewayHttp` pide
los datos del paciente al BC de Pacientes para la `Etiqueta` de cada paquete.

El archivo generado, `pacts/ms-catering-ms-pacientes.json`, se entrega al equipo
de ms-pacientes para que lo verifique en su pipeline. Como ese servicio no vive
en este repositorio, la verificación del provider queda pendiente de su lado.
"""
from uuid import UUID

import pytest
from pact import Pact, match

from catering.domain.exceptions import PacienteNoEncontradoError
from catering.infrastructure.gateways import PacienteGatewayHttp
from tests.contract.conftest import contrato_limpio, mock_server

pytestmark = pytest.mark.contract

CONSUMER = "ms-catering"
PROVIDER = "ms-pacientes"

PACIENTE_ID = "33333333-3333-4333-8333-333333333333"
PACIENTE_INEXISTENTE_ID = "88888888-8888-4888-8888-888888888888"


@pytest.fixture(scope="module", autouse=True)
def _regenerar_contrato(carpeta_pacts):
    contrato_limpio(carpeta_pacts, CONSUMER, PROVIDER)


@pytest.fixture
def pact(carpeta_pacts):
    pact = Pact(CONSUMER, PROVIDER).with_specification("V4")
    yield pact
    pact.write_file(carpeta_pacts, overwrite=False)


async def test_obtener_datos_de_paciente_existente_devuelve_los_datos_de_la_etiqueta(pact):
    # Arrange
    (
        pact.upon_receiving("una petición de los datos de un paciente existente")
        .given("existe el paciente", paciente_id=PACIENTE_ID)
        .with_request("GET", f"/pacientes/{PACIENTE_ID}")
        .with_header("Accept", "application/json")
        .will_respond_with(200)
        .with_body(
            {
                "id": match.uuid(PACIENTE_ID),
                "nombre": match.string("María Pérez"),
                "codigo": match.string("PAC-0001"),
                "numero_identificacion": match.string("1234567"),
            },
            content_type="application/json",
        )
    )

    with mock_server(pact) as servidor:
        # Act
        datos = await PacienteGatewayHttp(str(servidor.url)).obtener_datos(UUID(PACIENTE_ID))

    # Assert
    assert datos.nombre == "María Pérez"
    assert datos.codigo == "PAC-0001"
    assert datos.numero_identificacion == "1234567"


async def test_obtener_datos_de_paciente_inexistente_lanza_paciente_no_encontrado(pact):
    # Arrange
    (
        pact.upon_receiving("una petición de los datos de un paciente que no existe")
        .given("no existe el paciente", paciente_id=PACIENTE_INEXISTENTE_ID)
        .with_request("GET", f"/pacientes/{PACIENTE_INEXISTENTE_ID}")
        .with_header("Accept", "application/json")
        .will_respond_with(404)
    )

    with mock_server(pact) as servidor:
        # Act / Assert
        with pytest.raises(PacienteNoEncontradoError):
            await PacienteGatewayHttp(str(servidor.url)).obtener_datos(UUID(PACIENTE_INEXISTENTE_ID))
