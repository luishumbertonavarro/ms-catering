"""Contrato consumer: `app-paciente` → `ms-catering`.

Cada test declara una interacción (petición + respuesta esperada), la ejercita con
el `ClienteCalendarios` real contra el mock server de Pact y la agrega a
`pacts/app-paciente-ms-catering.json`.

El provider verifica este archivo en
`tests/contract/provider/test_verificar_calendarios_provider.py`.

Los valores concretos son solo ejemplos: los matchers (`match.*`) indican que el
provider debe devolver **ese tipo y esa forma**, no ese valor exacto.
"""
from uuid import UUID

import pytest
from pact import Pact, match

from tests.contract.conftest import contrato_limpio, mock_server
from tests.contract.consumer.cliente_calendarios import CalendarioNoEncontrado, ClienteCalendarios

pytestmark = pytest.mark.contract

CONSUMER = "app-paciente"
PROVIDER = "ms-catering"

# Identificadores fijos: el provider los recibe como parámetros del estado.
CALENDARIO_ID = "44444444-4444-4444-8444-444444444444"
PACIENTE_ID = "55555555-5555-4555-8555-555555555555"
PLAN_ID = "66666666-6666-4666-8666-666666666666"
CALENDARIO_INEXISTENTE_ID = "99999999-9999-4999-8999-999999999999"

ESTADO_CALENDARIO = r"^(ACTIVO|PAUSADO|COMPLETADO|CANCELADO)$"
ESTADO_ENTREGA = r"^(PROGRAMADA|SIN_ENTREGA|CANCELADA|ENTREGADA)$"


def calendario_esperado(calendario_id: str, paciente_id: str) -> dict:
    """Forma de `CalendarioResponse` que la app necesita para pintar el calendario."""
    return {
        "id": match.uuid(calendario_id),
        "paciente_id": match.uuid(paciente_id),
        "fecha_inicio": match.date("2099-01-01", "%Y-%m-%d"),
        "fecha_fin": match.date("2099-01-15", "%Y-%m-%d"),
        "estado": match.regex("ACTIVO", regex=ESTADO_CALENDARIO),
        "total_dias": match.integer(15),
        "plan_nutricional_id": match.uuid(PLAN_ID),
        "entregas": match.each_like(
            {
                "id": match.uuid(),
                "fecha": match.date("2099-01-01", "%Y-%m-%d"),
                "estado": match.regex("PROGRAMADA", regex=ESTADO_ENTREGA),
                "direccion": match.string("Av. Banzer 123"),
                "referencia": match.string("Portón verde"),
                "zona": match.string("Equipetrol"),
                "tiene_etiqueta": match.boolean(False),
            },
            min=1,
        ),
        "direcciones_habituales": match.each_like(
            {
                "id": match.uuid(),
                "nombre": match.string("trabajo"),
                "direccion": match.string("Calle Libertad 456"),
                "referencia": match.string("Oficina 3B"),
                "zona": match.string("Centro"),
                "es_principal": match.boolean(True),
            }
        ),
    }


@pytest.fixture(scope="module", autouse=True)
def _regenerar_contrato(carpeta_pacts):
    contrato_limpio(carpeta_pacts, CONSUMER, PROVIDER)


@pytest.fixture
def pact(carpeta_pacts):
    pact = Pact(CONSUMER, PROVIDER).with_specification("V4")
    yield pact
    pact.write_file(carpeta_pacts, overwrite=False)


async def test_obtener_calendario_existente_devuelve_sus_entregas_y_direcciones(pact):
    # Arrange
    (
        pact.upon_receiving("una petición para obtener un calendario existente")
        .given("existe un calendario activo", calendario_id=CALENDARIO_ID, paciente_id=PACIENTE_ID)
        .with_request("GET", f"/calendarios/{CALENDARIO_ID}")
        .with_header("Accept", "application/json")
        .will_respond_with(200)
        .with_body(calendario_esperado(CALENDARIO_ID, PACIENTE_ID), content_type="application/json")
    )

    with mock_server(pact) as servidor:
        # Act
        calendario = await ClienteCalendarios(servidor.url).obtener_calendario(UUID(CALENDARIO_ID))

    # Assert
    assert calendario["id"] == CALENDARIO_ID
    assert calendario["estado"] == "ACTIVO"
    assert calendario["entregas"][0]["direccion"]


async def test_obtener_calendario_de_un_paciente_devuelve_su_calendario_activo(pact):
    # Arrange
    (
        pact.upon_receiving("una petición para obtener el calendario de un paciente")
        .given("existe un calendario activo", calendario_id=CALENDARIO_ID, paciente_id=PACIENTE_ID)
        .with_request("GET", f"/calendarios/paciente/{PACIENTE_ID}")
        .with_header("Accept", "application/json")
        .will_respond_with(200)
        .with_body(calendario_esperado(CALENDARIO_ID, PACIENTE_ID), content_type="application/json")
    )

    with mock_server(pact) as servidor:
        # Act
        calendario = await ClienteCalendarios(servidor.url).obtener_calendario_paciente(UUID(PACIENTE_ID))

    # Assert
    assert calendario["paciente_id"] == PACIENTE_ID


async def test_obtener_calendario_inexistente_lanza_calendario_no_encontrado(pact):
    # Arrange
    (
        pact.upon_receiving("una petición para obtener un calendario que no existe")
        .given("no existe el calendario", calendario_id=CALENDARIO_INEXISTENTE_ID)
        .with_request("GET", f"/calendarios/{CALENDARIO_INEXISTENTE_ID}")
        .with_header("Accept", "application/json")
        .will_respond_with(404)
        .with_body({"detail": match.string("Calendario no encontrado.")}, content_type="application/json")
    )

    with mock_server(pact) as servidor:
        # Act / Assert
        with pytest.raises(CalendarioNoEncontrado):
            await ClienteCalendarios(servidor.url).obtener_calendario(UUID(CALENDARIO_INEXISTENTE_ID))
