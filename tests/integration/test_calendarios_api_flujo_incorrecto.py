"""Pruebas de integración del agregado CalendarioEntrega — flujos incorrectos.

Las pruebas unitarias ya comprueban que el dominio lanza la excepción correcta.
Lo que aquí se verifica es lo que ninguna de ellas puede ver:

1. Que los manejadores de `presentation/api/main.py` traducen cada excepción de
   dominio al **status HTTP y al código `tipo`** que promete el README.
2. Que tras un error **no queda nada escrito** en la base — es decir, que el
   `rollback` de `get_db_session` funciona de verdad. Es el equivalente
   integrado del `calendario_repo_mock.guardar.assert_not_awaited()` de las
   unitarias.

La última sección documenta **hallazgos**: peticiones que hoy no reciben un 4xx
sino que dejan escapar la excepción (un 500 en producción). No se modificó
`src/`; los tests fijan el comportamiento actual con `pytest.raises`, porque
`ASGITransport` re-lanza en el test la excepción que la app no manejó.
"""

from uuid import uuid4

import pytest
from sqlalchemy.exc import MultipleResultsFound

from catering.domain.exceptions import DireccionHabitualNoEncontradaError
from tests.integration.test_calendarios_api_flujo_correcto import (
    DIRECCION_TRABAJO,
    cuerpo_calendario,
    entrega_del,
)

pytestmark = pytest.mark.integration


async def _crear_calendario(cliente, **cambios) -> str:
    """Crea un calendario válido (2099, 15 días) y devuelve su id."""
    respuesta = await cliente.post("/calendarios", json=cuerpo_calendario(str(uuid4()), **cambios))
    assert respuesta.status_code == 201
    return respuesta.json()["id"]


# ---------------------------------------------------------------------------
# 404 — recursos que no existen
# ---------------------------------------------------------------------------

async def test_obtener_calendario_inexistente_devuelve_404(cliente):
    # Act
    respuesta = await cliente.get(f"/calendarios/{uuid4()}")

    # Assert — este 404 lo lanza el router con HTTPException: no trae `tipo`
    assert respuesta.status_code == 404
    assert "no encontrado" in respuesta.json()["detail"].lower()


async def test_obtener_calendario_de_un_paciente_sin_calendario_devuelve_404(cliente):
    # Act
    respuesta = await cliente.get(f"/calendarios/paciente/{uuid4()}")

    # Assert
    assert respuesta.status_code == 404
    assert "paciente" in respuesta.json()["detail"].lower()


async def test_listar_entregas_de_un_calendario_inexistente_devuelve_404(cliente):
    # Act
    respuesta = await cliente.get(f"/calendarios/{uuid4()}/entregas")

    # Assert
    assert respuesta.status_code == 404


async def test_cambiar_direccion_en_calendario_inexistente_devuelve_404(cliente):
    # Act
    respuesta = await cliente.patch(
        f"/calendarios/{uuid4()}/entregas/2099-01-05/direccion",
        json={"nueva_direccion": DIRECCION_TRABAJO},
    )

    # Assert
    assert respuesta.status_code == 404
    assert respuesta.json()["tipo"] == "CALENDARIO_NO_ENCONTRADO"


async def test_cancelar_calendario_inexistente_devuelve_404(cliente):
    # Act
    respuesta = await cliente.delete(f"/calendarios/{uuid4()}")

    # Assert
    assert respuesta.status_code == 404
    assert respuesta.json()["tipo"] == "CALENDARIO_NO_ENCONTRADO"


# ---------------------------------------------------------------------------
# 409 — conflictos con el estado actual del agregado
# ---------------------------------------------------------------------------

async def test_marcar_dos_veces_sin_entrega_el_mismo_dia_devuelve_409(cliente):
    # Arrange
    calendario_id = await _crear_calendario(cliente)
    await cliente.patch(f"/calendarios/{calendario_id}/entregas/2099-01-05/sin-entrega", json={})

    # Act
    respuesta = await cliente.patch(
        f"/calendarios/{calendario_id}/entregas/2099-01-05/sin-entrega", json={"motivo": "Otra vez"}
    )

    # Assert
    assert respuesta.status_code == 409
    assert respuesta.json()["tipo"] == "ENTREGA_NO_MODIFICABLE"

    # El primer marcado sigue ahí: el rollback del segundo no lo deshizo.
    calendario = (await cliente.get(f"/calendarios/{calendario_id}")).json()
    assert entrega_del(calendario, "2099-01-05")["estado"] == "SIN_ENTREGA"


async def test_cambiar_direccion_de_un_dia_sin_entrega_devuelve_409_y_no_la_cambia(cliente):
    # Arrange
    calendario_id = await _crear_calendario(cliente)
    await cliente.patch(f"/calendarios/{calendario_id}/entregas/2099-01-05/sin-entrega", json={})

    # Act
    respuesta = await cliente.patch(
        f"/calendarios/{calendario_id}/entregas/2099-01-05/direccion",
        json={"nueva_direccion": DIRECCION_TRABAJO},
    )

    # Assert
    assert respuesta.status_code == 409
    assert respuesta.json()["tipo"] == "ENTREGA_NO_MODIFICABLE"

    calendario = (await cliente.get(f"/calendarios/{calendario_id}")).json()
    assert entrega_del(calendario, "2099-01-05")["direccion"] == "Av. Banzer 123"


async def test_modificar_un_calendario_cancelado_devuelve_409_y_no_lo_altera(cliente):
    # Arrange
    calendario_id = await _crear_calendario(cliente)
    await cliente.delete(f"/calendarios/{calendario_id}")

    # Act
    respuesta = await cliente.patch(
        f"/calendarios/{calendario_id}/entregas/2099-01-05/direccion",
        json={"nueva_direccion": DIRECCION_TRABAJO},
    )

    # Assert
    assert respuesta.status_code == 409
    assert respuesta.json()["tipo"] == "CALENDARIO_INACTIVO"

    calendario = (await cliente.get(f"/calendarios/{calendario_id}")).json()
    assert entrega_del(calendario, "2099-01-05")["direccion"] == "Av. Banzer 123"
    assert entrega_del(calendario, "2099-01-05")["estado"] == "CANCELADA"


async def test_cancelar_dos_veces_un_calendario_devuelve_409(cliente):
    # Arrange
    calendario_id = await _crear_calendario(cliente)
    await cliente.delete(f"/calendarios/{calendario_id}")

    # Act
    respuesta = await cliente.delete(f"/calendarios/{calendario_id}")

    # Assert
    assert respuesta.status_code == 409
    assert respuesta.json()["tipo"] == "CALENDARIO_INACTIVO"


async def test_registrar_una_direccion_habitual_duplicada_devuelve_409_y_no_la_duplica(cliente):
    # Arrange
    calendario_id = await _crear_calendario(cliente)
    cuerpo = {"nombre": "trabajo", "direccion": DIRECCION_TRABAJO}
    await cliente.post(f"/calendarios/{calendario_id}/direcciones", json=cuerpo)

    # Act
    respuesta = await cliente.post(f"/calendarios/{calendario_id}/direcciones", json=cuerpo)

    # Assert
    assert respuesta.status_code == 409
    assert respuesta.json()["tipo"] == "DIRECCION_HABITUAL_DUPLICADA"

    direcciones = (await cliente.get(f"/calendarios/{calendario_id}/direcciones")).json()
    assert len(direcciones) == 1


# ---------------------------------------------------------------------------
# 422 — datos que violan una regla de negocio o el contrato de la API
# ---------------------------------------------------------------------------

async def test_cambiar_direccion_sin_dos_dias_de_anticipacion_devuelve_422(cliente):
    """HU-28. El calendario está en 2020: cualquier "hoy" es posterior a la entrega."""
    # Arrange
    calendario_id = await _crear_calendario(cliente, fecha_inicio="2020-01-01", fecha_fin="2020-01-15")

    # Act
    respuesta = await cliente.patch(
        f"/calendarios/{calendario_id}/entregas/2020-01-05/direccion",
        json={"nueva_direccion": DIRECCION_TRABAJO},
    )

    # Assert
    assert respuesta.status_code == 422
    assert respuesta.json()["tipo"] == "ANTICIPACION_INSUFICIENTE"

    calendario = (await cliente.get(f"/calendarios/{calendario_id}")).json()
    assert entrega_del(calendario, "2020-01-05")["direccion"] == "Av. Banzer 123"


async def test_marcar_sin_entrega_sin_dos_dias_de_anticipacion_devuelve_422(cliente):
    # Arrange
    calendario_id = await _crear_calendario(cliente, fecha_inicio="2020-01-01", fecha_fin="2020-01-15")

    # Act
    respuesta = await cliente.patch(
        f"/calendarios/{calendario_id}/entregas/2020-01-05/sin-entrega", json={}
    )

    # Assert
    assert respuesta.status_code == 422
    assert respuesta.json()["tipo"] == "ANTICIPACION_INSUFICIENTE"

    calendario = (await cliente.get(f"/calendarios/{calendario_id}")).json()
    assert entrega_del(calendario, "2020-01-05")["estado"] == "PROGRAMADA"


async def test_cambiar_direccion_de_una_fecha_fuera_del_calendario_devuelve_422(cliente):
    # Arrange
    calendario_id = await _crear_calendario(cliente)

    # Act — el calendario termina el 2099-01-15
    respuesta = await cliente.patch(
        f"/calendarios/{calendario_id}/entregas/2099-02-01/direccion",
        json={"nueva_direccion": DIRECCION_TRABAJO},
    )

    # Assert
    assert respuesta.status_code == 422
    assert respuesta.json()["tipo"] == "FECHA_FUERA_DE_RANGO"


async def test_crear_calendario_sin_paciente_id_devuelve_422_de_validacion(cliente):
    """Este 422 no lo produce el dominio, sino la validación de Pydantic."""
    # Arrange
    cuerpo = cuerpo_calendario(str(uuid4()))
    del cuerpo["paciente_id"]

    # Act
    respuesta = await cliente.post("/calendarios", json=cuerpo)

    # Assert
    assert respuesta.status_code == 422
    campos = [error["loc"][-1] for error in respuesta.json()["detail"]]
    assert "paciente_id" in campos


async def test_usar_una_fecha_mal_formada_en_la_ruta_devuelve_422_de_validacion(cliente):
    # Arrange
    calendario_id = await _crear_calendario(cliente)

    # Act
    respuesta = await cliente.patch(
        f"/calendarios/{calendario_id}/entregas/no-es-fecha/sin-entrega", json={}
    )

    # Assert
    assert respuesta.status_code == 422
    campos = [error["loc"][-1] for error in respuesta.json()["detail"]]
    assert "fecha" in campos


async def test_pedir_un_calendario_con_un_id_que_no_es_uuid_devuelve_422(cliente):
    # Act
    respuesta = await cliente.get("/calendarios/123")

    # Assert
    assert respuesta.status_code == 422


# ---------------------------------------------------------------------------
# Hallazgos — errores sin manejador HTTP (hoy terminan en 500)
# ---------------------------------------------------------------------------

async def test_asignar_una_direccion_habitual_inexistente_escapa_sin_manejador_http(cliente):
    """Hallazgo: `DireccionHabitualNoEncontradaError` no tiene manejador → 500.

    Debería ser un 404 con `tipo` propio. Igual que los demás errores, el
    rollback sí funciona: la entrega no cambia.
    """
    # Arrange
    calendario_id = await _crear_calendario(cliente)

    # Act / Assert
    with pytest.raises(DireccionHabitualNoEncontradaError):
        await cliente.patch(
            f"/calendarios/{calendario_id}/entregas/2099-01-05/direccion-habitual",
            json={"nombre_direccion": "gimnasio"},
        )

    calendario = (await cliente.get(f"/calendarios/{calendario_id}")).json()
    assert entrega_del(calendario, "2099-01-05")["direccion"] == "Av. Banzer 123"


async def test_crear_calendario_con_direccion_vacia_escapa_como_value_error(cliente):
    """Hallazgo: `DireccionEntrega` lanza `ValueError` y no hay manejador → 500.

    Pydantic acepta `""` porque el esquema no restringe la longitud; la regla
    vive en el VO. ms-plan-nutricional traduce ese caso a 422 `VALOR_INVALIDO`.
    """
    # Arrange
    paciente_id = str(uuid4())
    cuerpo = {**cuerpo_calendario(paciente_id), "direccion_inicial": {"direccion": "   "}}

    # Act / Assert
    with pytest.raises(ValueError, match="no puede estar vacía"):
        await cliente.post("/calendarios", json=cuerpo)

    respuesta = await cliente.get(f"/calendarios/paciente/{paciente_id}")
    assert respuesta.status_code == 404


async def test_dos_calendarios_activos_del_mismo_paciente_rompen_la_consulta_por_paciente(
    cliente,
):
    """Hallazgo: nada impide crear dos calendarios ACTIVOS para un paciente, y
    entonces `GET /calendarios/paciente/{id}` falla con `MultipleResultsFound`
    (`scalar_one_or_none()` en `obtener_por_paciente`) → 500.
    """
    # Arrange
    paciente_id = str(uuid4())
    primero = await cliente.post("/calendarios", json=cuerpo_calendario(paciente_id))
    segundo = await cliente.post(
        "/calendarios",
        json=cuerpo_calendario(paciente_id, fecha_inicio="2099-02-01", fecha_fin="2099-02-15"),
    )
    assert primero.status_code == segundo.status_code == 201

    # Act / Assert
    with pytest.raises(MultipleResultsFound):
        await cliente.get(f"/calendarios/paciente/{paciente_id}")
