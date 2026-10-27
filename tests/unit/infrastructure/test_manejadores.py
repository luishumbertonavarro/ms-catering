"""Reacciones de catering a eventos de otros servicios, contra el repositorio en memoria (sin BD)."""
from datetime import date
from uuid import uuid4

import pytest

from catering.domain.model import EstadoCalendario
from catering.domain.model.eventos import CalendarioEntregaCancelado, CalendarioEntregaCreado
from catering.infrastructure.messaging.manejadores import (
    DIRECCION_PROVISIONAL,
    MANEJADORES,
    REACCIONES,
    cancelar_calendario,
    completar_calendario,
    plan_nutricional_creado,
    servicio_contratado,
)
from catering.infrastructure.persistence.calendario_repository_mock import (
    InMemoryCalendarioRepository,
)


@pytest.fixture
def repo() -> InMemoryCalendarioRepository:
    return InMemoryCalendarioRepository()


def _contrato(paciente_id, tipo: str = "CATERING") -> dict:
    # Forma de ServicioContratadoIntegrationEvent (.NET, camelCase)
    return {
        "contratoId": str(uuid4()),
        "pacienteId": str(paciente_id),
        "pacienteNombre": "Ana Pérez",
        "nroIdentificacion": "1234567",
        "tipoServicio": tipo,
        "duracionDias": 15,
        "fechaInicio": "2026-01-01",
    }


async def _calendario_contratado(repo, paciente_id):
    await servicio_contratado(repo, _contrato(paciente_id))
    return await repo.obtener_por_paciente(paciente_id)


def test_el_servicio_escucha_los_eventos_acordados_por_el_grupo():
    # Act / Assert
    assert set(MANEJADORES) == set(REACCIONES) == {
        "servicio.contratado",
        "contrato.cancelado",
        "contrato.completado",
        "plan_nutricional.creado",
        "plan_nutricional.cancelado",
        "plan_nutricional.finalizado",
    }


async def test_servicio_contratado_de_catering_crea_el_calendario_del_periodo(repo):
    # Arrange
    paciente_id = uuid4()

    # Act
    calendario = await _calendario_contratado(repo, paciente_id)

    # Assert
    assert calendario.fecha_inicio == date(2026, 1, 1)
    assert calendario.fecha_fin == date(2026, 1, 15)
    assert calendario.total_dias == 15
    assert calendario.entregas[0].direccion == DIRECCION_PROVISIONAL
    assert [type(e) for e in calendario.eventos] == [CalendarioEntregaCreado]


async def test_servicio_contratado_con_calendario_activo_no_crea_otro(repo):
    # Arrange
    paciente_id = uuid4()
    primero = await _calendario_contratado(repo, paciente_id)

    # Act
    await servicio_contratado(repo, _contrato(paciente_id))

    # Assert
    assert await repo.obtener_por_paciente(paciente_id) is primero


@pytest.mark.parametrize("reaccion", [servicio_contratado, cancelar_calendario, completar_calendario])
async def test_contrato_que_no_es_de_catering_se_ignora(repo, reaccion):
    # Arrange
    paciente_id = uuid4()

    # Act
    await reaccion(repo, _contrato(paciente_id, tipo="ASESORAMIENTO"))

    # Assert
    assert await repo.obtener_por_paciente(paciente_id) is None


async def test_plan_nutricional_creado_se_vincula_al_calendario_activo(repo):
    # Arrange
    paciente_id = uuid4()
    calendario = await _calendario_contratado(repo, paciente_id)
    plan_id = uuid4()

    # Act
    await plan_nutricional_creado(repo, {"plan_id": str(plan_id), "paciente_id": str(paciente_id)})

    # Assert
    assert calendario.plan_nutricional_id == plan_id


async def test_plan_de_paciente_sin_calendario_se_ignora(repo):
    # Act / Assert — no lanza: el paciente puede no haber contratado catering
    await plan_nutricional_creado(repo, {"plan_id": str(uuid4()), "paciente_id": str(uuid4())})


async def test_plan_cancelado_cancela_el_calendario_y_anota_su_evento(repo):
    # Arrange
    paciente_id = uuid4()
    calendario = await _calendario_contratado(repo, paciente_id)
    calendario.extraer_eventos()

    # Act — PlanNutricionalCancelado no trae tipoServicio
    await cancelar_calendario(repo, {"plan_id": str(uuid4()), "paciente_id": str(paciente_id)})

    # Assert
    assert calendario.estado == EstadoCalendario.CANCELADO
    assert [type(e) for e in calendario.eventos] == [CalendarioEntregaCancelado]


async def test_contrato_completado_completa_el_calendario(repo):
    # Arrange
    paciente_id = uuid4()
    calendario = await _calendario_contratado(repo, paciente_id)

    # Act
    await completar_calendario(repo, _contrato(paciente_id))

    # Assert
    assert calendario.estado == EstadoCalendario.COMPLETADO


async def test_cancelacion_de_paciente_sin_calendario_se_ignora(repo):
    # Act / Assert
    await cancelar_calendario(repo, {"paciente_id": str(uuid4())})
    await completar_calendario(repo, {"paciente_id": str(uuid4())})
