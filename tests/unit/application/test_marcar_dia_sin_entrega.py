"""Pruebas del caso de uso `MarcarDiaSinEntregaUseCase` (HU-27)."""

from datetime import date
from uuid import uuid4

import pytest

from catering.application.commands import MarcarDiaSinEntregaCommand
from catering.application.use_cases import MarcarDiaSinEntregaUseCase
from catering.domain.exceptions import (
    AnticipacionInsuficienteError,
    CalendarioNoEncontradoError,
    EntregaNoModificableError,
)
from catering.domain.model import DiaSinEntrega, EstadoEntrega
from tests.conftest import FECHA_SOLICITUD_VALIDA

DIA_5 = date(2026, 1, 5)


async def test_marcar_dia_sin_entrega_registra_el_dia_con_su_motivo_y_persiste(
    calendario_repo_mock, construir_calendario
):
    # Arrange
    calendario = construir_calendario()
    calendario_repo_mock.obtener_por_id.return_value = calendario
    caso_de_uso = MarcarDiaSinEntregaUseCase(calendario_repo_mock)
    cmd = MarcarDiaSinEntregaCommand(
        calendario_id=calendario.id,
        fecha=DIA_5,
        fecha_solicitud=FECHA_SOLICITUD_VALIDA,
        motivo="Viaje de trabajo",
    )

    # Act
    await caso_de_uso.ejecutar(cmd)

    # Assert
    assert calendario.dias_sin_entrega == [DiaSinEntrega(DIA_5, "Viaje de trabajo")]
    entrega = next(e for e in calendario.entregas if e.fecha == DIA_5)
    assert entrega.estado is EstadoEntrega.SIN_ENTREGA
    calendario_repo_mock.obtener_por_id.assert_awaited_once_with(calendario.id)
    calendario_repo_mock.guardar.assert_awaited_once_with(calendario)


async def test_marcar_dia_sin_entrega_sin_motivo_usa_none_por_defecto(
    calendario_repo_mock, construir_calendario
):
    # Arrange
    calendario = construir_calendario()
    calendario_repo_mock.obtener_por_id.return_value = calendario
    caso_de_uso = MarcarDiaSinEntregaUseCase(calendario_repo_mock)

    # Act
    await caso_de_uso.ejecutar(
        MarcarDiaSinEntregaCommand(calendario.id, DIA_5, FECHA_SOLICITUD_VALIDA)
    )

    # Assert
    assert calendario.dias_sin_entrega[0].motivo is None


async def test_marcar_dia_sin_entrega_en_calendario_inexistente_lanza_error_y_no_persiste(
    calendario_repo_mock,
):
    # Arrange
    calendario_repo_mock.obtener_por_id.return_value = None
    caso_de_uso = MarcarDiaSinEntregaUseCase(calendario_repo_mock)

    # Act / Assert
    with pytest.raises(CalendarioNoEncontradoError):
        await caso_de_uso.ejecutar(
            MarcarDiaSinEntregaCommand(uuid4(), DIA_5, FECHA_SOLICITUD_VALIDA)
        )

    calendario_repo_mock.guardar.assert_not_awaited()


async def test_marcar_dos_veces_el_mismo_dia_lanza_error_y_no_persiste(
    calendario_repo_mock, construir_calendario
):
    # Arrange
    calendario = construir_calendario()
    calendario.marcar_dia_sin_entrega(DIA_5, FECHA_SOLICITUD_VALIDA)
    calendario_repo_mock.obtener_por_id.return_value = calendario
    caso_de_uso = MarcarDiaSinEntregaUseCase(calendario_repo_mock)

    # Act / Assert
    with pytest.raises(EntregaNoModificableError):
        await caso_de_uso.ejecutar(
            MarcarDiaSinEntregaCommand(calendario.id, DIA_5, FECHA_SOLICITUD_VALIDA)
        )

    calendario_repo_mock.guardar.assert_not_awaited()


async def test_marcar_dia_sin_entrega_con_un_dia_de_anticipacion_no_persiste(
    calendario_repo_mock, construir_calendario
):
    # Arrange
    calendario = construir_calendario()
    calendario_repo_mock.obtener_por_id.return_value = calendario
    caso_de_uso = MarcarDiaSinEntregaUseCase(calendario_repo_mock)

    # Act / Assert
    with pytest.raises(AnticipacionInsuficienteError):
        await caso_de_uso.ejecutar(
            MarcarDiaSinEntregaCommand(calendario.id, DIA_5, date(2026, 1, 4))
        )

    calendario_repo_mock.guardar.assert_not_awaited()
