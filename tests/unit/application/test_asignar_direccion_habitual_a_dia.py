"""Pruebas del caso de uso `AsignarDireccionHabitualADiaUseCase` (HU-30)."""

from datetime import date
from uuid import uuid4

import pytest

from catering.application.commands import AsignarDireccionHabitualADiaCommand
from catering.application.use_cases import AsignarDireccionHabitualADiaUseCase
from catering.domain.exceptions import (
    AnticipacionInsuficienteError,
    CalendarioNoEncontradoError,
    DireccionHabitualNoEncontradaError,
)
from tests.conftest import FECHA_SOLICITUD_VALIDA

DIA_5 = date(2026, 1, 5)


async def test_asignar_direccion_habitual_copia_la_direccion_al_dia_y_persiste(
    calendario_repo_mock, construir_calendario, direccion_trabajo
):
    # Arrange
    calendario = construir_calendario()
    calendario.registrar_direccion_habitual("trabajo", direccion_trabajo)
    calendario_repo_mock.obtener_por_id.return_value = calendario
    caso_de_uso = AsignarDireccionHabitualADiaUseCase(calendario_repo_mock)

    # Act
    await caso_de_uso.ejecutar(
        AsignarDireccionHabitualADiaCommand(calendario.id, DIA_5, "trabajo", FECHA_SOLICITUD_VALIDA)
    )

    # Assert
    entrega = next(e for e in calendario.entregas if e.fecha == DIA_5)
    assert entrega.direccion == direccion_trabajo
    calendario_repo_mock.obtener_por_id.assert_awaited_once_with(calendario.id)
    calendario_repo_mock.guardar.assert_awaited_once_with(calendario)


async def test_asignar_direccion_en_calendario_inexistente_lanza_error_y_no_persiste(
    calendario_repo_mock,
):
    # Arrange
    calendario_repo_mock.obtener_por_id.return_value = None
    caso_de_uso = AsignarDireccionHabitualADiaUseCase(calendario_repo_mock)

    # Act / Assert
    with pytest.raises(CalendarioNoEncontradoError):
        await caso_de_uso.ejecutar(
            AsignarDireccionHabitualADiaCommand(uuid4(), DIA_5, "trabajo", FECHA_SOLICITUD_VALIDA)
        )

    calendario_repo_mock.guardar.assert_not_awaited()


async def test_asignar_una_direccion_habitual_no_registrada_lanza_error_y_no_persiste(
    calendario_repo_mock, construir_calendario
):
    # Arrange
    calendario = construir_calendario()
    calendario_repo_mock.obtener_por_id.return_value = calendario
    caso_de_uso = AsignarDireccionHabitualADiaUseCase(calendario_repo_mock)

    # Act / Assert
    with pytest.raises(DireccionHabitualNoEncontradaError):
        await caso_de_uso.ejecutar(
            AsignarDireccionHabitualADiaCommand(calendario.id, DIA_5, "gimnasio", FECHA_SOLICITUD_VALIDA)
        )

    calendario_repo_mock.guardar.assert_not_awaited()


async def test_asignar_direccion_habitual_sin_anticipacion_no_persiste(
    calendario_repo_mock, construir_calendario, direccion_trabajo
):
    # Arrange
    calendario = construir_calendario()
    calendario.registrar_direccion_habitual("trabajo", direccion_trabajo)
    calendario_repo_mock.obtener_por_id.return_value = calendario
    caso_de_uso = AsignarDireccionHabitualADiaUseCase(calendario_repo_mock)

    # Act / Assert
    with pytest.raises(AnticipacionInsuficienteError):
        await caso_de_uso.ejecutar(
            AsignarDireccionHabitualADiaCommand(calendario.id, DIA_5, "trabajo", date(2026, 1, 4))
        )

    calendario_repo_mock.guardar.assert_not_awaited()
