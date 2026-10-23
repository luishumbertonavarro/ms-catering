"""Pruebas de la traducción de errores de dominio a respuestas HTTP.

`presentation/api/main.py` registra, con `@app.exception_handler`, un manejador
por excepción de dominio. Cada uno devuelve un `JSONResponse` con `status_code`
y un código `tipo` estable que el cliente puede interpretar sin parsear el mensaje.

**Por qué es una prueba unitaria y no de integración.** Starlette deja los
manejadores accesibles en `app.exception_handlers`, y ninguno usa el `request`.
Se pueden invocar directamente: sin cliente HTTP y sin base de datos (importar la
app no abre ninguna conexión). Lo que se prueba aquí es **la tabla de
traducción**. Que FastAPI enrute de verdad una excepción hasta su manejador
durante una petición real lo cubre
`tests/integration/test_calendarios_api_flujo_incorrecto.py`, que es otra cosa.
"""

import json
from datetime import date
from uuid import uuid4

import pytest

from catering.domain import exceptions as excepciones_de_dominio
from catering.domain.exceptions import (
    AnticipacionInsuficienteError,
    CalendarioInactivoError,
    CalendarioNoEncontradoError,
    CateringDomainError,
    DireccionHabitualDuplicadaError,
    DireccionHabitualNoEncontradaError,
    EntregaNoEncontradaError,
    EntregaNoModificableError,
    FechaFueraDeRangoError,
    PacienteNoEncontradoError,
)
from catering.presentation.api.main import app

# Tabla de traducción: (excepción ya construida, status HTTP, código `tipo`).
# Es el contrato público del microservicio frente a sus clientes.
CASOS = [
    # 404 — el recurso no existe
    (CalendarioNoEncontradoError(uuid4()), 404, "CALENDARIO_NO_ENCONTRADO"),
    (EntregaNoEncontradaError(date(2026, 1, 5)), 404, "ENTREGA_NO_ENCONTRADA"),
    (PacienteNoEncontradoError(uuid4()), 404, "PACIENTE_NO_ENCONTRADO"),
    # 409 — conflicto con el estado actual del recurso
    (EntregaNoModificableError(date(2026, 1, 5), "SIN_ENTREGA"), 409, "ENTREGA_NO_MODIFICABLE"),
    (CalendarioInactivoError("CANCELADO"), 409, "CALENDARIO_INACTIVO"),
    (DireccionHabitualDuplicadaError("trabajo"), 409, "DIRECCION_HABITUAL_DUPLICADA"),
    # 422 — la petición es coherente pero viola una regla de negocio
    (
        AnticipacionInsuficienteError(date(2026, 1, 5), date(2026, 1, 4)),
        422,
        "ANTICIPACION_INSUFICIENTE",
    ),
    (
        FechaFueraDeRangoError(date(2026, 2, 1), date(2026, 1, 1), date(2026, 1, 15)),
        422,
        "FECHA_FUERA_DE_RANGO",
    ),
]

# Excepciones de dominio que HOY no tienen manejador (ver el test que lo documenta).
SIN_MANEJADOR_CONOCIDO = {DireccionHabitualNoEncontradaError}


@pytest.mark.parametrize(
    ("excepcion", "status_esperado", "tipo_esperado"),
    CASOS,
    ids=[tipo for _, _, tipo in CASOS],
)
async def test_cada_excepcion_de_dominio_se_traduce_al_status_y_tipo_esperados(
    excepcion, status_esperado, tipo_esperado
):
    # Arrange
    manejador = app.exception_handlers[type(excepcion)]

    # Act — los manejadores no usan el `request`, por eso se pasa None
    respuesta = await manejador(None, excepcion)

    # Assert
    cuerpo = json.loads(respuesta.body)
    assert respuesta.status_code == status_esperado
    assert cuerpo["tipo"] == tipo_esperado
    assert cuerpo["detail"] == str(excepcion)


async def test_el_detalle_de_la_respuesta_reproduce_el_mensaje_del_dominio():
    # Arrange — el mensaje lo escribe el dominio; la capa HTTP no lo reescribe
    calendario_id = uuid4()
    excepcion = CalendarioNoEncontradoError(calendario_id)
    manejador = app.exception_handlers[CalendarioNoEncontradoError]

    # Act
    respuesta = await manejador(None, excepcion)

    # Assert
    cuerpo = json.loads(respuesta.body)
    assert str(calendario_id) in cuerpo["detail"]


def test_toda_excepcion_de_dominio_declarada_tiene_un_manejador_registrado():
    """Red de seguridad: una excepción nueva sin manejador acabaría en un 500.

    Recorre las excepciones que exporta `domain.exceptions` y exige que cada una
    esté registrada, **salvo** las de `SIN_MANEJADOR_CONOCIDO`, que tienen su
    propio test documentando el hueco. Si mañana se añade otra y se olvida el
    manejador, este test lo dice antes de que un cliente reciba un error opaco.
    """
    # Arrange
    declaradas = {
        getattr(excepciones_de_dominio, nombre)
        for nombre in excepciones_de_dominio.__all__
    } - {CateringDomainError} - SIN_MANEJADOR_CONOCIDO

    # Act
    registradas = set(app.exception_handlers)

    # Assert
    assert declaradas <= registradas, (
        "Sin manejador HTTP: "
        f"{sorted(e.__name__ for e in declaradas - registradas)}"
    )


def test_direccion_habitual_no_encontrada_no_tiene_manejador_y_acaba_en_500():
    """Hallazgo: `DireccionHabitualNoEncontradaError` no tiene manejador.

    `PATCH /calendarios/{id}/entregas/{fecha}/direccion-habitual` con un nombre
    no registrado responde **500** en lugar de 404. No se modificó `src/`: este
    test fija el comportamiento actual. El día que se registre el manejador,
    fallará — entonces hay que moverla a `CASOS` y vaciar `SIN_MANEJADOR_CONOCIDO`.
    """
    # Act / Assert
    assert DireccionHabitualNoEncontradaError not in app.exception_handlers


def test_un_value_error_del_dominio_no_tiene_manejador_y_acaba_en_500():
    """Hallazgo: `DireccionEntrega` lanza `ValueError` ante una dirección vacía y
    no hay un manejador genérico de `ValueError` (ms-plan-nutricional sí lo tiene
    y responde 422 `VALOR_INVALIDO`). Hoy esa petición termina en 500."""
    # Act / Assert
    assert ValueError not in app.exception_handlers


def test_los_casos_probados_cubren_todas_las_excepciones_con_manejador():
    """Evita que la tabla `CASOS` se quede atrás respecto a los manejadores."""
    # Arrange
    probadas = {type(excepcion) for excepcion, _, _ in CASOS}
    registradas = {
        clase
        for clase in app.exception_handlers
        if isinstance(clase, type) and issubclass(clase, CateringDomainError)
    }

    # Act / Assert
    assert registradas == probadas
