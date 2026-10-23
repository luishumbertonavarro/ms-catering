"""Pruebas del caso de uso `CrearCalendarioUseCase`.

Es el único comando que no lee del repositorio: construye el agregado con la
factoría `CalendarioEntrega.crear()` y lo guarda.
"""

from datetime import date
from uuid import uuid4

import pytest

from catering.application.commands import CrearCalendarioCommand, DireccionData
from catering.application.use_cases import CrearCalendarioUseCase
from catering.domain.model import DireccionEntrega, EstadoCalendario, EstadoEntrega


def _cmd(**cambios) -> CrearCalendarioCommand:
    valores = {
        "paciente_id": uuid4(),
        "fecha_inicio": date(2026, 1, 1),
        "fecha_fin": date(2026, 1, 15),
        "direccion_inicial": DireccionData(
            direccion="Av. Banzer 123", referencia="Portón verde", zona="Equipetrol"
        ),
    }
    valores.update(cambios)
    return CrearCalendarioCommand(**valores)


async def test_crear_calendario_devuelve_el_calendario_y_lo_persiste(calendario_repo_mock):
    # Arrange
    cmd = _cmd()
    caso_de_uso = CrearCalendarioUseCase(calendario_repo_mock)

    # Act
    calendario = await caso_de_uso.ejecutar(cmd)

    # Assert
    assert calendario.paciente_id == cmd.paciente_id
    assert calendario.estado is EstadoCalendario.ACTIVO
    assert calendario.total_dias == 15
    calendario_repo_mock.guardar.assert_awaited_once_with(calendario)


async def test_crear_calendario_traduce_la_direccion_inicial_al_value_object(
    calendario_repo_mock,
):
    # Arrange
    caso_de_uso = CrearCalendarioUseCase(calendario_repo_mock)

    # Act
    calendario = await caso_de_uso.ejecutar(_cmd())

    # Assert — DireccionData (DTO de aplicación) → DireccionEntrega (VO de dominio)
    esperada = DireccionEntrega(direccion="Av. Banzer 123", referencia="Portón verde", zona="Equipetrol")
    assert all(e.direccion == esperada for e in calendario.entregas)
    assert all(e.estado is EstadoEntrega.PROGRAMADA for e in calendario.entregas)


async def test_crear_calendario_propaga_el_plan_nutricional_a_las_entregas(calendario_repo_mock):
    # Arrange
    plan_id = uuid4()
    caso_de_uso = CrearCalendarioUseCase(calendario_repo_mock)

    # Act
    calendario = await caso_de_uso.ejecutar(_cmd(plan_nutricional_id=plan_id))

    # Assert
    assert calendario.plan_nutricional_id == plan_id
    assert all(e.plan_nutricional_id == plan_id for e in calendario.entregas)


async def test_crear_calendario_no_consulta_el_repositorio_antes_de_guardar(calendario_repo_mock):
    # Arrange
    caso_de_uso = CrearCalendarioUseCase(calendario_repo_mock)

    # Act
    await caso_de_uso.ejecutar(_cmd())

    # Assert — es un comando de creación pura: nada de lecturas previas
    calendario_repo_mock.obtener_por_id.assert_not_awaited()
    calendario_repo_mock.obtener_por_paciente.assert_not_awaited()


async def test_crear_calendario_no_verifica_si_el_paciente_ya_tiene_uno_activo(
    calendario_repo_mock,
):
    """Hallazgo: nada impide dos calendarios ACTIVOS para el mismo paciente.

    El caso de uso no consulta `obtener_por_paciente`. Con dos activos, el
    repositorio real hace `scalar_one_or_none()` y `GET /calendarios/paciente/{id}`
    falla con `MultipleResultsFound` (lo documenta
    `tests/integration/test_calendarios_api_flujo_incorrecto.py`).
    """
    # Arrange
    paciente_id = uuid4()
    caso_de_uso = CrearCalendarioUseCase(calendario_repo_mock)

    # Act
    primero = await caso_de_uso.ejecutar(_cmd(paciente_id=paciente_id))
    segundo = await caso_de_uso.ejecutar(_cmd(paciente_id=paciente_id))

    # Assert
    assert primero.id != segundo.id
    assert calendario_repo_mock.guardar.await_count == 2


async def test_crear_calendario_con_direccion_vacia_lanza_value_error_y_no_persiste(
    calendario_repo_mock,
):
    # Arrange
    caso_de_uso = CrearCalendarioUseCase(calendario_repo_mock)

    # Act / Assert
    with pytest.raises(ValueError):
        await caso_de_uso.ejecutar(_cmd(direccion_inicial=DireccionData(direccion="")))

    calendario_repo_mock.guardar.assert_not_awaited()
