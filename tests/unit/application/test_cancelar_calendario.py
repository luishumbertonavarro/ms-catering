"""Pruebas del caso de uso `CancelarCalendarioUseCase`."""

from uuid import uuid4

import pytest

from catering.application.commands import CancelarCalendarioCommand
from catering.application.use_cases import CancelarCalendarioUseCase
from catering.domain.exceptions import CalendarioInactivoError, CalendarioNoEncontradoError
from catering.domain.model import EstadoCalendario, EstadoEntrega


async def test_cancelar_calendario_activo_lo_cancela_en_cascada_y_persiste(
    calendario_repo_mock, construir_calendario
):
    # Arrange
    calendario = construir_calendario()
    calendario_repo_mock.obtener_por_id.return_value = calendario
    caso_de_uso = CancelarCalendarioUseCase(calendario_repo_mock)

    # Act
    await caso_de_uso.ejecutar(CancelarCalendarioCommand(calendario_id=calendario.id))

    # Assert
    assert calendario.estado is EstadoCalendario.CANCELADO
    assert all(e.estado is EstadoEntrega.CANCELADA for e in calendario.entregas)
    calendario_repo_mock.obtener_por_id.assert_awaited_once_with(calendario.id)
    calendario_repo_mock.guardar.assert_awaited_once_with(calendario)


async def test_cancelar_calendario_inexistente_lanza_error_y_no_persiste(calendario_repo_mock):
    # Arrange
    calendario_repo_mock.obtener_por_id.return_value = None
    caso_de_uso = CancelarCalendarioUseCase(calendario_repo_mock)

    # Act / Assert
    with pytest.raises(CalendarioNoEncontradoError):
        await caso_de_uso.ejecutar(CancelarCalendarioCommand(calendario_id=uuid4()))

    calendario_repo_mock.guardar.assert_not_awaited()


@pytest.mark.parametrize(
    "estado",
    [EstadoCalendario.CANCELADO, EstadoCalendario.COMPLETADO, EstadoCalendario.PAUSADO],
    ids=lambda e: e.value,
)
async def test_cancelar_un_calendario_no_activo_lanza_error_y_no_persiste(
    calendario_repo_mock, construir_calendario, estado
):
    # Arrange
    calendario = construir_calendario(estado=estado)
    calendario_repo_mock.obtener_por_id.return_value = calendario
    caso_de_uso = CancelarCalendarioUseCase(calendario_repo_mock)

    # Act / Assert
    with pytest.raises(CalendarioInactivoError):
        await caso_de_uso.ejecutar(CancelarCalendarioCommand(calendario_id=calendario.id))

    calendario_repo_mock.guardar.assert_not_awaited()
