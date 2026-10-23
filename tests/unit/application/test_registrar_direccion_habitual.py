"""Pruebas del caso de uso `RegistrarDireccionHabitualUseCase` (HU-30)."""

from uuid import uuid4

import pytest

from catering.application.commands import DireccionData, RegistrarDireccionHabitualCommand
from catering.application.use_cases import RegistrarDireccionHabitualUseCase
from catering.domain.exceptions import CalendarioNoEncontradoError, DireccionHabitualDuplicadaError
from catering.domain.model import DireccionEntrega

TRABAJO = DireccionData(direccion="Calle Libertad 456", referencia="Oficina 3B", zona="Centro")


async def test_registrar_direccion_habitual_la_agrega_al_calendario_y_persiste(
    calendario_repo_mock, construir_calendario
):
    # Arrange
    calendario = construir_calendario()
    calendario_repo_mock.obtener_por_id.return_value = calendario
    caso_de_uso = RegistrarDireccionHabitualUseCase(calendario_repo_mock)

    # Act
    await caso_de_uso.ejecutar(
        RegistrarDireccionHabitualCommand(calendario.id, "trabajo", TRABAJO, es_principal=True)
    )

    # Assert
    [habitual] = calendario.direcciones_habituales
    assert habitual.nombre == "trabajo"
    assert habitual.es_principal is True
    assert habitual.direccion == DireccionEntrega("Calle Libertad 456", "Oficina 3B", "Centro")
    calendario_repo_mock.obtener_por_id.assert_awaited_once_with(calendario.id)
    calendario_repo_mock.guardar.assert_awaited_once_with(calendario)


async def test_registrar_direccion_habitual_sin_indicar_principal_la_deja_no_principal(
    calendario_repo_mock, construir_calendario
):
    # Arrange
    calendario = construir_calendario()
    calendario_repo_mock.obtener_por_id.return_value = calendario
    caso_de_uso = RegistrarDireccionHabitualUseCase(calendario_repo_mock)

    # Act
    await caso_de_uso.ejecutar(RegistrarDireccionHabitualCommand(calendario.id, "trabajo", TRABAJO))

    # Assert
    assert calendario.direcciones_habituales[0].es_principal is False


async def test_registrar_direccion_en_calendario_inexistente_lanza_error_y_no_persiste(
    calendario_repo_mock,
):
    # Arrange
    calendario_repo_mock.obtener_por_id.return_value = None
    caso_de_uso = RegistrarDireccionHabitualUseCase(calendario_repo_mock)

    # Act / Assert
    with pytest.raises(CalendarioNoEncontradoError):
        await caso_de_uso.ejecutar(RegistrarDireccionHabitualCommand(uuid4(), "trabajo", TRABAJO))

    calendario_repo_mock.guardar.assert_not_awaited()


async def test_registrar_direccion_habitual_duplicada_lanza_error_y_no_persiste(
    calendario_repo_mock, construir_calendario, direccion_trabajo
):
    # Arrange
    calendario = construir_calendario()
    calendario.registrar_direccion_habitual("trabajo", direccion_trabajo)
    calendario_repo_mock.obtener_por_id.return_value = calendario
    caso_de_uso = RegistrarDireccionHabitualUseCase(calendario_repo_mock)

    # Act / Assert
    with pytest.raises(DireccionHabitualDuplicadaError):
        await caso_de_uso.ejecutar(RegistrarDireccionHabitualCommand(calendario.id, "trabajo", TRABAJO))

    calendario_repo_mock.guardar.assert_not_awaited()


async def test_registrar_una_direccion_habitual_vacia_lanza_value_error_y_no_persiste(
    calendario_repo_mock, construir_calendario
):
    # Arrange
    calendario = construir_calendario()
    calendario_repo_mock.obtener_por_id.return_value = calendario
    caso_de_uso = RegistrarDireccionHabitualUseCase(calendario_repo_mock)

    # Act / Assert
    with pytest.raises(ValueError):
        await caso_de_uso.ejecutar(
            RegistrarDireccionHabitualCommand(calendario.id, "trabajo", DireccionData(direccion=""))
        )

    calendario_repo_mock.guardar.assert_not_awaited()
