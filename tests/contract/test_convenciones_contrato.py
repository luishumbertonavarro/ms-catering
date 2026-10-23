"""Guardián automático de las reglas del entorno de pruebas de contrato (Pact).

Es el equivalente de `tests/integration/test_convenciones_del_entorno.py` para
`tests/contract/`. Cada test comprueba una regla declarada en
`.claude/skills/contract-testing-catering/SKILL.md` y
`.claude/agents/pact-writer.md`. Así, un contrato generado por IA que la incumpla
se detecta en el acto.

No lleva el marcador `contract` ni necesita Docker: es análisis estático de los
archivos de test y de los pacts ya generados.
"""

import json
import re
from pathlib import Path

from tests.integration.test_convenciones_del_entorno import codigo_efectivo

CARPETA_CONTRATO = Path(__file__).resolve().parent
RAIZ = CARPETA_CONTRATO.parents[1]
CARPETA_PACTS = RAIZ / "pacts"
CARPETA_CONSUMER = CARPETA_CONTRATO / "consumer"
CARPETA_PROVIDER = CARPETA_CONTRATO / "provider"
APP_PROVIDER = CARPETA_PROVIDER / "app_provider.py"
MAIN_REAL = RAIZ / "src" / "catering" / "presentation" / "api" / "main.py"

# Pacts que este repositorio verifica como provider.
PROVIDER_PROPIO = "ms-catering"
MINIMO_INTERACCIONES = 2


def archivos_consumer() -> list[Path]:
    return sorted(CARPETA_CONSUMER.glob("test_*.py"))


def archivos_de_contrato() -> list[Path]:
    return [*archivos_consumer(), *sorted(CARPETA_PROVIDER.glob("test_*.py"))]


def pacts() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(CARPETA_PACTS.glob("*.json"))]


def test_hay_tests_y_pacts_que_revisar():
    """Red de seguridad: sin archivos, todo lo demás pasaría sin comprobar nada."""
    # Act / Assert
    assert len(archivos_consumer()) >= 1, "No hay tests consumer en tests/contract/consumer."
    assert list(CARPETA_PROVIDER.glob("test_*.py")), "No hay verificación del provider."
    assert pacts(), "No hay pacts en pacts/. Genéralos con: uv run pytest tests/contract/consumer"


# ---------------------------------------------------------------------------
# Regla 1 — cada contrato es significativo
# ---------------------------------------------------------------------------

def test_cada_pact_tiene_al_menos_dos_interacciones():
    """Requisito de la actividad: al menos dos solicitudes por relación."""
    # Act
    cortos = [
        f"{p['consumer']['name']}-{p['provider']['name']}: {len(p['interactions'])}"
        for p in pacts()
        if len(p["interactions"]) < MINIMO_INTERACCIONES
    ]

    # Assert
    assert not cortos, f"Pacts con menos de {MINIMO_INTERACCIONES} interacciones: {cortos}"


def test_todas_las_interacciones_declaran_un_provider_state():
    """Sin `given(...)`, el provider no sabe qué datos preparar y la verificación
    depende del contenido accidental de la base."""
    # Act
    sin_estado = [
        i["description"]
        for p in pacts()
        for i in p["interactions"]
        if not i.get("providerStates")
    ]

    # Assert
    assert not sin_estado, f"Interacciones sin provider state: {sin_estado}"


def test_las_respuestas_con_cuerpo_usan_matchers():
    """Sin matchers, el contrato exige valores exactos (ids, fechas) y se rompe
    con cualquier dato distinto, aunque el formato sea correcto."""
    # Act
    sin_matchers = [
        i["description"]
        for p in pacts()
        for i in p["interactions"]
        if i["response"].get("body") and not i["response"].get("matchingRules")
    ]

    # Assert
    assert not sin_matchers, f"Respuestas con valores literales sin matchers: {sin_matchers}"


# ---------------------------------------------------------------------------
# Regla 2 — el consumer usa código cliente real
# ---------------------------------------------------------------------------

def test_los_tests_consumer_no_usan_mocks_ni_httpx_directo():
    """El contrato debe salir del cliente real (`ClienteCalendarios`,
    `PacienteGatewayHttp`). Si el test hace la petición a mano, el contrato no
    refleja lo que el cliente de verdad envía."""
    # Arrange
    prohibidos = ("AsyncMock", "MagicMock", "unittest.mock", "monkeypatch", "httpx.")

    # Act
    infractores = [
        f"{archivo.name}: {termino}"
        for archivo in archivos_consumer()
        for termino in prohibidos
        if termino in codigo_efectivo(archivo)
    ]

    # Assert
    assert not infractores, f"Tests consumer con peticiones a mano o mocks: {infractores}"


def test_los_tests_consumer_escriben_el_pact_y_usan_el_mock_server_estable():
    """`mock_server` evita el falso "Missing request" del núcleo de Pact en Windows."""
    # Act
    infractores = [
        archivo.name
        for archivo in archivos_consumer()
        if "write_file(" not in (codigo := codigo_efectivo(archivo))
        or "mock_server(pact)" not in codigo
        or "pact.serve(" in codigo
    ]

    # Assert
    assert not infractores, f"Tests consumer sin write_file o sin mock_server: {infractores}"


# ---------------------------------------------------------------------------
# Regla 3 — el provider cubre todos los estados y no ensucia la base
# ---------------------------------------------------------------------------

def test_cada_provider_state_de_los_pacts_propios_tiene_handler():
    """Un estado sin handler hace fallar la verificación con un 400 poco claro."""
    # Arrange
    handlers = codigo_efectivo(APP_PROVIDER)
    estados = {
        estado["name"]
        for p in pacts()
        if p["provider"]["name"] == PROVIDER_PROPIO
        for i in p["interactions"]
        for estado in i.get("providerStates", [])
    }

    # Act
    sin_handler = sorted(e for e in estados if f'"{e}":' not in handlers)

    # Assert
    assert not sin_handler, f"Provider states sin handler en app_provider.py: {sin_handler}"


def test_la_app_del_provider_revierte_todo_y_no_borra_datos():
    # Arrange
    codigo = codigo_efectivo(APP_PROVIDER)
    destructivas = re.compile(r"\b(TRUNCATE|DROP\s+(TABLE|DATABASE)|DELETE\s+FROM|\.delete\()", re.IGNORECASE)

    # Act / Assert
    assert 'join_transaction_mode="create_savepoint"' in codigo
    assert "await transaccion.rollback()" in codigo, "Sin rollback final, la verificación deja filas."
    assert "begin_nested()" in codigo, "Cada interacción debe aislarse con su propio SAVEPOINT."
    assert not destructivas.search(codigo), "El aislamiento es por rollback, nunca por borrado."


def test_la_ruta_de_provider_states_no_existe_en_la_app_real():
    """La ruta de estados escribe en la base: jamás debe llegar a producción."""
    # Act
    infractores = [
        archivo.name
        for archivo in (RAIZ / "src").rglob("*.py")
        if "provider-states" in archivo.read_text(encoding="utf-8")
    ]

    # Assert
    assert MAIN_REAL.is_file()
    assert not infractores, f"Código de producción con la ruta de estados de Pact: {infractores}"


def test_la_verificacion_se_omite_si_no_hay_base_de_datos():
    # Act
    contenido = "".join(p.read_text(encoding="utf-8") for p in CARPETA_PROVIDER.glob("test_*.py"))

    # Assert
    assert "pytest.skip" in contenido


# ---------------------------------------------------------------------------
# Regla 4 — convenciones de escritura
# ---------------------------------------------------------------------------

def test_todos_los_archivos_de_contrato_llevan_el_marcador_contract():
    # Act
    sin_marcador = [
        archivo.name
        for archivo in archivos_de_contrato()
        if "pytestmark = pytest.mark.contract" not in archivo.read_text(encoding="utf-8")
    ]

    # Assert
    assert not sin_marcador, f"Archivos sin `pytestmark = pytest.mark.contract`: {sin_marcador}"


def test_los_nombres_de_los_tests_de_contrato_son_descriptivos():
    # Arrange
    definicion = re.compile(r"^(?:async )?def (test_\w+)", re.MULTILINE)

    # Act
    cortos = [
        nombre
        for archivo in archivos_de_contrato()
        for nombre in definicion.findall(codigo_efectivo(archivo))
        if len(nombre.split("_")) < 5
    ]

    # Assert
    assert not cortos, f"Nombres que no describen acción, condición y resultado: {cortos}"
