"""Guardián automático de las reglas del entorno de pruebas de integración.

Un entorno de pruebas para IA no está *validado* porque las reglas estén escritas
en un README o en una skill: está validado cuando **la máquina las comprueba**.
Este archivo es esa comprobación.

Cada test de aquí verifica una de las reglas que declaran
`.claude/skills/integration-testing-catering/SKILL.md` y
`.claude/agents/integration-test-writer.md`. Si un test generado por IA —o por una
persona con prisa— rompe una de ellas, la suite lo detecta en el acto en vez de
descubrirlo semanas después con datos borrados de la base de desarrollo.

Estos tests **no llevan el marcador `integration` y no tocan la base de datos**:
son análisis estático de los propios archivos. Así siguen protegiendo el
repositorio aunque no haya Docker levantado.
"""

import ast
import json
import re
from pathlib import Path

CARPETA_INTEGRACION = Path(__file__).resolve().parent
RAIZ = CARPETA_INTEGRACION.parents[1]
CONFTEST = CARPETA_INTEGRACION / "conftest.py"
COLECCION_POSTMAN = RAIZ / "postman" / "ms-catering.postman_collection.json"


def archivos_de_test() -> list[Path]:
    """Los `test_*.py` de la carpeta, excluyendo este mismo guardián.

    La exclusión es necesaria: este archivo menciona `AsyncMock`, `TRUNCATE` y
    demás dentro de sus propios patrones de búsqueda, y se detectaría a sí mismo.
    """
    propio = Path(__file__).resolve()
    return [p for p in CARPETA_INTEGRACION.glob("test_*.py") if p.resolve() != propio]


def codigo_efectivo(archivo: Path) -> str:
    """Devuelve el archivo con sus docstrings y comentarios eliminados.

    Es la pieza que hace útiles a los tests de abajo. Sin ella, una explicación
    perfectamente legítima —"esto sustituye al `calendario_repo_mock` de las
    unitarias"— se detectaría como una infracción, y la forma de "arreglarlo"
    sería empeorar la documentación.

    Se conservan las cadenas normales a propósito: un `TRUNCATE` dentro de un
    `text("...")` es código ejecutable y **sí** debe detectarse.
    """
    fuente = archivo.read_text(encoding="utf-8")
    lineas = fuente.splitlines()

    lineas_de_docstring: set[int] = set()
    for nodo in ast.walk(ast.parse(fuente)):
        if not isinstance(nodo, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        primero = nodo.body[0] if nodo.body else None
        if (
            isinstance(primero, ast.Expr)
            and isinstance(primero.value, ast.Constant)
            and isinstance(primero.value.value, str)
        ):
            lineas_de_docstring.update(range(primero.lineno, primero.end_lineno + 1))

    # Los comentarios se quitan con una regex: aproximación suficiente aquí,
    # donde ninguna cadena contiene almohadillas.
    return "\n".join(
        "" if numero in lineas_de_docstring else re.sub(r"#.*$", "", linea)
        for numero, linea in enumerate(lineas, start=1)
    )


def test_hay_archivos_de_test_que_revisar():
    """Red de seguridad: si el glob deja de encontrar archivos, todo lo demás
    pasaría en verde sin comprobar nada."""
    # Act
    archivos = archivos_de_test()

    # Assert
    assert len(archivos) >= 2, "Se esperaban al menos los dos archivos de flujo."


# ---------------------------------------------------------------------------
# Regla 1 — cero mocks
# ---------------------------------------------------------------------------

def test_ninguna_prueba_de_integracion_usa_mocks():
    """Si hay un mock, no es una prueba de integración: es una unitaria mal
    ubicada, y estaría ocultando justo la capa que se quiere probar."""
    # Arrange
    prohibidos = ("AsyncMock", "MagicMock", "unittest.mock", "monkeypatch")

    # Act
    infractores = [
        f"{archivo.name}: {termino}"
        for archivo in archivos_de_test()
        for termino in prohibidos
        if termino in codigo_efectivo(archivo)
    ]

    # Assert
    assert not infractores, (
        "Las pruebas de integración no admiten dobles de prueba. "
        f"Encontrado: {infractores}"
    )


def test_las_pruebas_de_integracion_no_usan_las_fixtures_de_las_unitarias():
    """`tests/conftest.py` sirve a las unitarias (builders de dominio y dobles de
    los puertos). Son mundos separados y mezclarlos rompe el aislamiento."""
    # Arrange
    fixtures_de_unitarias = (
        "calendario_repo_mock",
        "construir_calendario",
        "direccion_domicilio",
        "direccion_trabajo",
        "FECHA_SOLICITUD_VALIDA",
    )

    # Act
    infractores = [
        f"{archivo.name}: {fixture}"
        for archivo in archivos_de_test()
        for fixture in fixtures_de_unitarias
        if fixture in codigo_efectivo(archivo)
    ]

    # Assert
    assert not infractores, f"Fixtures de unitarias usadas en integración: {infractores}"


# ---------------------------------------------------------------------------
# Regla 2 — no ensuciar ni destruir la base de datos
# ---------------------------------------------------------------------------

def test_ninguna_prueba_borra_datos_de_la_base():
    """El aislamiento lo da el rollback de la transacción, no un borrado.

    Un `TRUNCATE` aquí no solo sería redundante: destruiría los datos de
    desarrollo de quien ejecute la suite.
    """
    # Arrange
    sentencias_destructivas = re.compile(
        r"\b(TRUNCATE|DROP\s+(TABLE|DATABASE)|DELETE\s+FROM|CREATE\s+DATABASE)\b",
        re.IGNORECASE,
    )

    # Act
    infractores = [
        f"{archivo.name}: {match.group(0)}"
        for archivo in [*archivos_de_test(), CONFTEST]
        for match in sentencias_destructivas.finditer(codigo_efectivo(archivo))
    ]

    # Assert
    assert not infractores, (
        "Ninguna prueba de integración puede borrar ni crear bases o tablas: "
        f"el rollback ya aísla cada test. Encontrado: {infractores}"
    )


def test_el_conftest_aisla_cada_test_con_una_transaccion_reversible():
    """Comprueba que las tres piezas del aislamiento siguen en su sitio.

    Si alguien quita el `create_savepoint`, el `commit()` de cada petición pasaría
    a escribir de verdad en `db_catering` y la suite empezaría a dejar basura sin
    que ningún test fallara. Por eso se verifica explícitamente.
    """
    # Arrange
    contenido = CONFTEST.read_text(encoding="utf-8")

    # Act / Assert
    assert 'join_transaction_mode="create_savepoint"' in contenido, (
        "Sin `create_savepoint`, el commit() de la aplicación escribiría de verdad."
    )
    assert "await transaccion.rollback()" in contenido, (
        "Sin el rollback final, cada test dejaría filas en la base."
    )
    assert "dependency_overrides[get_db_session]" in contenido, (
        "La app debe redirigirse por `get_db_session`, la única hoja compartida."
    )


def test_el_conftest_omite_las_pruebas_si_no_hay_base_de_datos():
    """Quien no tenga Docker levantado debe poder correr la suite igualmente."""
    # Arrange
    contenido = CONFTEST.read_text(encoding="utf-8")

    # Act / Assert
    assert "pytest.skip" in contenido


# ---------------------------------------------------------------------------
# Regla 3 — convenciones de escritura
# ---------------------------------------------------------------------------

def test_todos_los_archivos_llevan_el_marcador_integration():
    """Es lo que permite `uv run pytest -m integration` y lo que documenta que
    ese archivo necesita PostgreSQL."""
    # Act
    sin_marcador = [
        archivo.name
        for archivo in archivos_de_test()
        if "pytestmark = pytest.mark.integration" not in archivo.read_text(encoding="utf-8")
    ]

    # Assert
    assert not sin_marcador, f"Archivos sin `pytestmark`: {sin_marcador}"


def test_los_nombres_de_los_tests_estan_en_espanol_y_describen_el_resultado():
    """Convención del proyecto: `test_<accion>_<condicion>_<resultado_esperado>`.

    Se aproxima exigiendo un nombre suficientemente descriptivo: al menos cuatro
    palabras. `test_cancelar_calendario` no dice qué se espera;
    `test_cancelar_dos_veces_un_calendario_devuelve_409` sí.
    """
    # Arrange
    definicion = re.compile(r"^async def (test_\w+)", re.MULTILINE)

    # Act
    demasiado_cortos = [
        nombre
        for archivo in archivos_de_test()
        for nombre in definicion.findall(codigo_efectivo(archivo))
        if len(nombre.split("_")) < 5
    ]

    # Assert
    assert not demasiado_cortos, (
        "Estos nombres no describen acción, condición y resultado esperado: "
        f"{demasiado_cortos}"
    )


def test_las_pruebas_no_dependen_de_la_fecha_actual():
    """Un test que dependa de "hoy" deja de ser determinista."""
    # Arrange
    fechas_dinamicas = re.compile(r"\b(date\.today|datetime\.now|datetime\.utcnow)\b")

    # Act
    infractores = [
        archivo.name
        for archivo in archivos_de_test()
        if fechas_dinamicas.search(codigo_efectivo(archivo))
    ]

    # Assert
    assert not infractores, f"Usan la fecha actual en vez de una fija: {infractores}"


def test_los_calendarios_de_prueba_estan_en_fechas_lejanas_al_presente():
    """Regla propia de catering: la anticipación de 2 días no debe depender de "hoy".

    Los endpoints de modificación usan `date.today()` como fecha de solicitud.
    Para que un test no pase hoy y falle dentro de un mes, los calendarios de
    integración viven en el futuro lejano (2099, siempre modificables) o en el
    pasado (2020, nunca modificables). 2026 solo aparece en
    `verificar-modificacion`, que recibe ambas fechas explícitas.
    """
    # Arrange
    fecha = re.compile(r"\b(20\d\d)-\d\d-\d\d\b")
    anios_permitidos = {"2020", "2026", "2099"}

    # Act
    infractores = [
        f"{archivo.name}: {match.group(0)}"
        for archivo in archivos_de_test()
        for match in fecha.finditer(codigo_efectivo(archivo))
        if match.group(1) not in anios_permitidos
    ]

    # Assert
    assert not infractores, f"Fechas cercanas al presente en integración: {infractores}"


def test_el_flujo_incorrecto_verifica_el_codigo_tipo_y_no_solo_el_status():
    """Un 409 a secas no distingue `ENTREGA_NO_MODIFICABLE` de `CALENDARIO_INACTIVO`.

    El código `tipo` es el contrato que producen los manejadores de `main.py`, y
    es lo que estas pruebas existen para verificar.
    """
    # Arrange
    archivo = CARPETA_INTEGRACION / "test_calendarios_api_flujo_incorrecto.py"
    contenido = archivo.read_text(encoding="utf-8")

    # Act
    comprobaciones_de_tipo = contenido.count('["tipo"]')
    comprobaciones_de_status = contenido.count("status_code ==")

    # Assert — no todas las respuestas traen `tipo` (los 422 de Pydantic y los
    # 404 del router no), pero la mayoría debe verificarlo.
    assert comprobaciones_de_tipo >= comprobaciones_de_status / 2, (
        f"Solo {comprobaciones_de_tipo} comprobaciones de `tipo` frente a "
        f"{comprobaciones_de_status} de status: se está verificando el status a secas."
    )


# ---------------------------------------------------------------------------
# Regla 4 — la colección de Postman acompaña a los tests
# ---------------------------------------------------------------------------

def test_la_coleccion_de_postman_existe_y_es_json_valido():
    # Act / Assert
    assert COLECCION_POSTMAN.is_file(), f"Falta {COLECCION_POSTMAN}"
    json.loads(COLECCION_POSTMAN.read_text(encoding="utf-8"))


def test_la_coleccion_de_postman_cubre_el_flujo_correcto_y_el_incorrecto():
    """El enunciado del taller exige ambos flujos; esto impide que uno se pierda
    en una edición posterior."""
    # Arrange
    coleccion = json.loads(COLECCION_POSTMAN.read_text(encoding="utf-8"))

    # Act
    carpetas = [item["name"] for item in coleccion["item"]]

    # Assert
    assert any("correcto" in nombre.lower() for nombre in carpetas), carpetas
    assert any("incorrecto" in nombre.lower() for nombre in carpetas), carpetas


def test_todas_las_peticiones_de_postman_tienen_aserciones():
    """Una petición sin `pm.test` no prueba nada: solo llama al endpoint."""
    # Arrange
    coleccion = json.loads(COLECCION_POSTMAN.read_text(encoding="utf-8"))

    def peticiones_sin_aserciones(items: list[dict], ruta: str = "") -> list[str]:
        huerfanas = []
        for item in items:
            nombre = f"{ruta}/{item['name']}"
            if "item" in item:  # es una carpeta: se baja un nivel
                huerfanas += peticiones_sin_aserciones(item["item"], nombre)
                continue
            scripts = [
                linea
                for evento in item.get("event", [])
                if evento.get("listen") == "test"
                for linea in evento["script"]["exec"]
            ]
            if not any("pm.test" in linea for linea in scripts):
                huerfanas.append(nombre)
        return huerfanas

    # Act
    huerfanas = peticiones_sin_aserciones(coleccion["item"])

    # Assert
    assert not huerfanas, f"Peticiones de Postman sin `pm.test`: {huerfanas}"
