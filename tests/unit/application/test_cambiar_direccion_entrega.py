"""Pruebas del caso de uso `CambiarDireccionEntregaUseCase` — ejemplo de referencia de mocking.

Este archivo es el patrón que siguen los demás casos de uso. Todos comparten la
misma estructura:

    1. recuperar el agregado del repositorio (`obtener_por_id`)
    2. si no existe, lanzar `CalendarioNoEncontradoError`
    3. invocar el método de dominio
    4. persistir (`guardar`)

El repositorio real habla con PostgreSQL. En una prueba unitaria se sustituye por
un **mock** (`AsyncMock(spec=CalendarioEntregaRepository)`, definido en
`tests/conftest.py`), lo que permite:

  * controlar la entrada  → `calendario_repo_mock.obtener_por_id.return_value = calendario`
  * verificar la salida   → `calendario_repo_mock.guardar.assert_awaited_once_with(calendario)`

sin levantar ninguna base de datos.
"""

from datetime import date
from uuid import uuid4

import pytest

from catering.application.commands import CambiarDireccionEntregaCommand, DireccionData
from catering.application.use_cases import CambiarDireccionEntregaUseCase
from catering.domain.exceptions import (
    AnticipacionInsuficienteError,
    CalendarioInactivoError,
    CalendarioNoEncontradoError,
    FechaFueraDeRangoError,
)
from catering.domain.model import DireccionEntrega, EstadoCalendario
from tests.conftest import FECHA_SOLICITUD_VALIDA

DIA_5 = date(2026, 1, 5)
NUEVA = DireccionData(direccion="Calle Libertad 456", referencia="Oficina 3B", zona="Centro")


def _cmd(calendario_id, fecha=DIA_5, fecha_solicitud=FECHA_SOLICITUD_VALIDA, nueva=NUEVA):
    return CambiarDireccionEntregaCommand(
        calendario_id=calendario_id,
        fecha_entrega=fecha,
        nueva_direccion=nueva,
        fecha_solicitud=fecha_solicitud,
    )


async def test_cambiar_direccion_valida_actualiza_la_entrega_y_persiste_el_calendario(
    calendario_repo_mock, construir_calendario
):
    # Arrange — el mock devuelve el calendario que decidimos, sin tocar la base de datos
    calendario = construir_calendario()
    calendario_repo_mock.obtener_por_id.return_value = calendario
    caso_de_uso = CambiarDireccionEntregaUseCase(calendario_repo_mock)

    # Act
    await caso_de_uso.ejecutar(_cmd(calendario.id))

    # Assert — se verifica el resultado y también CÓMO se usó la dependencia
    entrega = next(e for e in calendario.entregas if e.fecha == DIA_5)
    assert entrega.direccion == DireccionEntrega(
        direccion="Calle Libertad 456", referencia="Oficina 3B", zona="Centro"
    )
    calendario_repo_mock.obtener_por_id.assert_awaited_once_with(calendario.id)
    calendario_repo_mock.guardar.assert_awaited_once_with(calendario)


async def test_cambiar_direccion_en_calendario_inexistente_lanza_error_y_no_persiste(
    calendario_repo_mock,
):
    # Arrange — devolver None es la forma de simular "el calendario no existe"
    calendario_repo_mock.obtener_por_id.return_value = None
    caso_de_uso = CambiarDireccionEntregaUseCase(calendario_repo_mock)
    calendario_id = uuid4()

    # Act / Assert
    with pytest.raises(CalendarioNoEncontradoError, match=str(calendario_id)):
        await caso_de_uso.ejecutar(_cmd(calendario_id))

    # El caso de uso debe cortar antes de intentar guardar nada
    calendario_repo_mock.guardar.assert_not_awaited()


async def test_cambiar_direccion_sin_anticipacion_propaga_el_error_del_dominio(
    calendario_repo_mock, construir_calendario
):
    # Arrange
    calendario = construir_calendario()
    calendario_repo_mock.obtener_por_id.return_value = calendario
    caso_de_uso = CambiarDireccionEntregaUseCase(calendario_repo_mock)

    # Act / Assert — la regla la impone el agregado, no el caso de uso
    with pytest.raises(AnticipacionInsuficienteError):
        await caso_de_uso.ejecutar(_cmd(calendario.id, fecha_solicitud=date(2026, 1, 4)))

    calendario_repo_mock.guardar.assert_not_awaited()


async def test_cambiar_direccion_fuera_de_rango_no_persiste(
    calendario_repo_mock, construir_calendario
):
    # Arrange
    calendario = construir_calendario()
    calendario_repo_mock.obtener_por_id.return_value = calendario
    caso_de_uso = CambiarDireccionEntregaUseCase(calendario_repo_mock)

    # Act / Assert
    with pytest.raises(FechaFueraDeRangoError):
        await caso_de_uso.ejecutar(_cmd(calendario.id, fecha=date(2026, 3, 1)))

    calendario_repo_mock.guardar.assert_not_awaited()


async def test_cambiar_direccion_en_calendario_cancelado_no_persiste(
    calendario_repo_mock, construir_calendario
):
    # Arrange
    calendario = construir_calendario(estado=EstadoCalendario.CANCELADO)
    calendario_repo_mock.obtener_por_id.return_value = calendario
    caso_de_uso = CambiarDireccionEntregaUseCase(calendario_repo_mock)

    # Act / Assert
    with pytest.raises(CalendarioInactivoError):
        await caso_de_uso.ejecutar(_cmd(calendario.id))

    calendario_repo_mock.guardar.assert_not_awaited()


async def test_cambiar_a_una_direccion_vacia_lanza_value_error_y_no_persiste(
    calendario_repo_mock, construir_calendario
):
    # Arrange — el caso de uso construye el VO, y el VO valida
    calendario = construir_calendario()
    calendario_repo_mock.obtener_por_id.return_value = calendario
    caso_de_uso = CambiarDireccionEntregaUseCase(calendario_repo_mock)

    # Act / Assert
    with pytest.raises(ValueError, match="no puede estar vacía"):
        await caso_de_uso.ejecutar(_cmd(calendario.id, nueva=DireccionData(direccion="  ")))

    calendario_repo_mock.guardar.assert_not_awaited()


def test_el_mock_con_spec_rechaza_metodos_que_no_existen_en_el_puerto(calendario_repo_mock):
    """Demuestra por qué `spec=CalendarioEntregaRepository` es obligatorio.

    Con `spec`, el mock solo acepta los métodos que declara el puerto. Sin él,
    cualquier método mal escrito devolvería otro mock y el test pasaría en verde
    ocultando el error.
    """
    # Act / Assert — método inexistente en el puerto
    with pytest.raises(AttributeError):
        calendario_repo_mock.obtener_por_idd
