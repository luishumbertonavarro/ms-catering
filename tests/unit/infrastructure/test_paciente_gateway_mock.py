"""Pruebas del gateway mock hacia el Bounded Context de Pacientes.

`PacienteGateway` es un **puerto de anticorrupción**: el dominio de catering no
conoce a ms-pacientes, solo esta abstracción. Sus datos alimentan la `Etiqueta`
del paquete. `PacienteGatewayMock` devuelve datos falsos pero deterministas.

Es una prueba unitaria legítima pese a vivir en `infrastructure/`: el mock no
hace ninguna llamada de red ni toca la base de datos, es una función pura sobre
el UUID del paciente. El adaptador real, `PacienteGatewayHttp`, sí hace red: lo
cubre el contrato consumer de `tests/contract/`.
"""

from uuid import UUID, uuid4

import pytest

from catering.domain.gateways import DatosPacienteExterno, PacienteGateway
from catering.infrastructure.gateways import PacienteGatewayHttp, PacienteGatewayMock


async def test_el_gateway_mock_deriva_los_datos_del_uuid_del_paciente():
    # Arrange
    paciente_id = UUID("12345678-1234-5678-1234-567812345678")
    gateway = PacienteGatewayMock()

    # Act
    datos = await gateway.obtener_datos(paciente_id)

    # Assert — el código son los 8 primeros caracteres del UUID en mayúsculas
    assert isinstance(datos, DatosPacienteExterno)
    assert datos.codigo == "12345678"
    assert datos.nombre == "Paciente Mock 12345678"
    assert datos.numero_identificacion == "000000001234"


async def test_el_gateway_mock_devuelve_siempre_lo_mismo_para_el_mismo_paciente():
    # Arrange — sin determinismo, los tests que lo usen serían inestables
    paciente_id = uuid4()
    gateway = PacienteGatewayMock()

    # Act
    primera = await gateway.obtener_datos(paciente_id)
    segunda = await gateway.obtener_datos(paciente_id)

    # Assert — `DatosPacienteExterno` es frozen, así que compara por valor
    assert primera == segunda


async def test_el_gateway_mock_distingue_a_dos_pacientes_distintos():
    # Arrange
    gateway = PacienteGatewayMock()

    # Act
    uno = await gateway.obtener_datos(UUID("aaaaaaaa-0000-4000-8000-000000000000"))
    otro = await gateway.obtener_datos(UUID("bbbbbbbb-0000-4000-8000-000000000000"))

    # Assert
    assert uno.codigo != otro.codigo


@pytest.mark.parametrize("implementacion", [PacienteGatewayMock, PacienteGatewayHttp])
def test_los_adaptadores_de_pacientes_implementan_el_puerto_del_dominio(implementacion):
    # Act / Assert — la inversión de dependencias se sostiene: infra depende del puerto
    assert issubclass(implementacion, PacienteGateway)


def test_el_puerto_de_pacientes_es_abstracto_y_no_se_puede_instanciar():
    # Act / Assert — es un contrato, no una implementación
    with pytest.raises(TypeError):
        PacienteGateway()


def test_el_adaptador_http_normaliza_la_barra_final_de_la_url_base():
    # Act — construirlo no hace ninguna petición
    gateway = PacienteGatewayHttp("http://ms-pacientes:8000/", timeout=2.0)

    # Assert
    assert gateway._base_url == "http://ms-pacientes:8000"
    assert gateway._timeout == 2.0
