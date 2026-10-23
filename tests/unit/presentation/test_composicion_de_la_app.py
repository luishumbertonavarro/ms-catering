"""Pruebas del cableado de la aplicación FastAPI.

Estas pruebas afirman **cómo está compuesto el microservicio**, no qué hace cada
endpoint: que el router de calendarios está montado, que el contrato OpenAPI se
genera con todas las rutas declaradas, que la dependencia de repositorio anuncia
el *puerto* del dominio (y no la implementación concreta), que las rutas fijas
no quedan tapadas por `/{calendario_id}` y que la fábrica de sesiones apunta a
la base configurada.

**No necesitan PostgreSQL.** `create_async_engine` no abre ninguna conexión al
construirse, `Settings` trae valores por defecto y el `lifespan` solo se ejecuta
cuando arranca un servidor. Importar la app es, por tanto, una operación pura.

Qué NO cubren, a propósito: el cuerpo de los endpoints y el SQL del repositorio.
Eso exige una petición real contra una base real y vive en `tests/integration/`.
"""

import inspect

from fastapi.routing import APIRoute

from catering.domain.repositories import CalendarioEntregaRepository
from catering.domain.services import ValidadorCambioCalendarioService
from catering.infrastructure.config import settings
from catering.infrastructure.persistence.database import AsyncSessionFactory, engine
from catering.presentation.api.main import app
from catering.presentation.api.routers import calendarios

# (método, ruta) de cada endpoint publicado: es el contrato de la API.
ENDPOINTS = {
    ("POST", "/calendarios"),
    ("GET", "/calendarios"),
    ("GET", "/calendarios/entregas/fecha/{fecha}"),
    ("GET", "/calendarios/verificar-modificacion"),
    ("GET", "/calendarios/paciente/{paciente_id}"),
    ("GET", "/calendarios/{calendario_id}"),
    ("DELETE", "/calendarios/{calendario_id}"),
    ("GET", "/calendarios/{calendario_id}/entregas"),
    ("PATCH", "/calendarios/{calendario_id}/entregas/{fecha}/direccion"),
    ("PATCH", "/calendarios/{calendario_id}/entregas/{fecha}/sin-entrega"),
    ("PATCH", "/calendarios/{calendario_id}/entregas/{fecha}/direccion-habitual"),
    ("POST", "/calendarios/{calendario_id}/direcciones"),
    ("GET", "/calendarios/{calendario_id}/direcciones"),
}


def _endpoints_de_la_app() -> set[tuple[str, str]]:
    """Endpoints que la app publica de verdad, leídos de su contrato OpenAPI.

    Desde FastAPI 0.13x, `app.routes` ya no expone las rutas de un router
    incluido (las envuelve en un objeto interno). El OpenAPI es la vista pública
    y estable de lo que la app sirve.
    """
    return {
        (metodo.upper(), ruta)
        for ruta, operaciones in app.openapi()["paths"].items()
        for metodo in operaciones
    }


def test_la_app_monta_el_router_de_calendarios():
    # Arrange / Act
    prefijos = {ruta.split("/")[1] for _, ruta in _endpoints_de_la_app()}

    # Assert
    assert prefijos == {"calendarios"}
    assert all(isinstance(r, APIRoute) for r in calendarios.router.routes)


def test_la_app_declara_exactamente_los_endpoints_del_contrato():
    # Arrange / Act
    publicados = _endpoints_de_la_app()

    # Assert — ni faltan ni sobran: un endpoint nuevo obliga a actualizar el contrato
    assert publicados == ENDPOINTS, (
        f"Faltan: {sorted(ENDPOINTS - publicados)} · Sobran: {sorted(publicados - ENDPOINTS)}"
    )


def test_el_contrato_openapi_se_genera_e_incluye_las_rutas_publicadas():
    # Arrange / Act — generar el esquema ejercita todos los modelos de respuesta
    esquema = app.openapi()

    # Assert
    assert esquema["info"]["title"] == "ms-catering — NUR-TRICENTER"
    for _, ruta in ENDPOINTS:
        assert ruta in esquema["paths"], f"{ruta} no aparece en el OpenAPI"
    componentes = esquema["components"]["schemas"]
    assert {
        "CalendarioResponse",
        "EntregaResponse",
        "DireccionHabitualResponse",
        "VerificarModificacionResponse",
    } <= set(componentes)


def test_las_rutas_fijas_se_declaran_antes_que_la_ruta_con_calendario_id():
    """Si `/calendarios/{calendario_id}` se registrara primero, FastAPI intentaría
    convertir "verificar-modificacion" o "paciente" en un UUID y respondería 422.
    El orden de declaración en el router es lo que lo evita."""
    # Arrange — el orden de evaluación es el de declaración en el router
    rutas_get = [r.path for r in calendarios.router.routes if "GET" in r.methods]

    # Act
    posicion_comodin = rutas_get.index("/calendarios/{calendario_id}")

    # Assert
    for fija in (
        "/calendarios/entregas/fecha/{fecha}",
        "/calendarios/verificar-modificacion",
        "/calendarios/paciente/{paciente_id}",
    ):
        assert rutas_get.index(fija) < posicion_comodin, fija


def test_el_router_inyecta_el_puerto_del_dominio_y_no_la_implementacion():
    """Protege la inversión de dependencias en el punto donde es fácil romperla.

    Si alguien anotara `-> CalendarioEntregaRepositoryImpl`, la capa de
    presentación pasaría a depender de SQLAlchemy y la arquitectura dejaría de
    sostenerse. El tipo de retorno declarado es lo que documenta esa frontera.
    """
    # Act
    anotacion = inspect.signature(calendarios._get_repo).return_annotation

    # Assert
    assert anotacion is CalendarioEntregaRepository


def test_el_proveedor_del_validador_entrega_el_servicio_de_dominio():
    # Act
    servicio = calendarios._get_validador_service()

    # Assert — el endpoint de verificación no necesita base de datos
    assert isinstance(servicio, ValidadorCambioCalendarioService)
    assert "session" not in inspect.signature(calendarios._get_validador_service).parameters


def test_la_fabrica_de_sesiones_apunta_a_la_base_de_datos_configurada():
    # Arrange / Act — construir el engine no abre ninguna conexión
    url = engine.url.render_as_string(hide_password=False)

    # Assert
    assert url == settings.database_url
    assert url.startswith("postgresql+asyncpg://")
    assert AsyncSessionFactory.kw["bind"] is engine
    # `expire_on_commit=False` es lo que permite leer el agregado tras el commit
    assert AsyncSessionFactory.kw["expire_on_commit"] is False
