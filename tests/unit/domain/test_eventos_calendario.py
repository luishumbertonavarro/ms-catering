"""Eventos de dominio que anota CalendarioEntrega y que el repositorio pasa al outbox."""
from datetime import date
from uuid import uuid4

import pytest

from catering.domain.exceptions import AnticipacionInsuficienteError, CalendarioInactivoError
from catering.domain.model import EstadoCalendario, EstadoEntrega
from catering.domain.model.eventos import (
    CalendarioEntregaCancelado,
    CalendarioEntregaCompletado,
    CalendarioEntregaCreado,
    DiaSinEntregaMarcado,
    DireccionEntregaCambiada,
)
from tests.conftest import FECHA_SOLICITUD_VALIDA

DIA_5 = date(2026, 1, 5)


def _tipos(eventos) -> list[type]:
    return [type(e) for e in eventos]


def test_crear_calendario_anota_calendario_entrega_creado_con_la_direccion_inicial(
    construir_calendario, direccion_domicilio
):
    # Arrange / Act
    calendario = construir_calendario()

    # Assert
    assert _tipos(calendario.eventos) == [CalendarioEntregaCreado]
    assert calendario.eventos[0].calendario_id == calendario.id
    assert calendario.eventos[0].direccion_entrega == direccion_domicilio


def test_extraer_eventos_devuelve_los_pendientes_y_los_vacia(construir_calendario):
    # Arrange
    calendario = construir_calendario()

    # Act
    eventos = calendario.extraer_eventos()

    # Assert
    assert _tipos(eventos) == [CalendarioEntregaCreado]
    assert calendario.eventos == []


def test_cambiar_direccion_anota_direccion_entrega_cambiada_con_anterior_y_nueva(
    construir_calendario, direccion_domicilio, direccion_trabajo
):
    # Arrange
    calendario = construir_calendario()
    calendario.extraer_eventos()

    # Act
    calendario.cambiar_direccion_entrega(DIA_5, direccion_trabajo, FECHA_SOLICITUD_VALIDA)

    # Assert
    [evento] = calendario.eventos
    assert isinstance(evento, DireccionEntregaCambiada)
    assert evento.fecha_entrega == DIA_5
    assert evento.origen == "MANUAL"
    assert evento.nombre_direccion_habitual is None
    assert evento.direccion_anterior == direccion_domicilio
    assert evento.direccion_nueva == direccion_trabajo


def test_asignar_direccion_habitual_anota_cambio_con_origen_direccion_habitual(
    construir_calendario, direccion_trabajo
):
    # Arrange
    calendario = construir_calendario()
    calendario.registrar_direccion_habitual("trabajo", direccion_trabajo)
    calendario.extraer_eventos()

    # Act
    calendario.asignar_direccion_habitual_a_dia(DIA_5, "trabajo", FECHA_SOLICITUD_VALIDA)

    # Assert
    [evento] = calendario.eventos
    assert evento.origen == "DIRECCION_HABITUAL"
    assert evento.nombre_direccion_habitual == "trabajo"
    assert evento.direccion_nueva == direccion_trabajo


def test_registrar_direccion_habitual_no_anota_eventos(construir_calendario, direccion_trabajo):
    # Arrange
    calendario = construir_calendario()
    calendario.extraer_eventos()

    # Act
    calendario.registrar_direccion_habitual("trabajo", direccion_trabajo)

    # Assert
    assert calendario.eventos == []


def test_marcar_dia_sin_entrega_anota_dia_sin_entrega_marcado(construir_calendario):
    # Arrange
    calendario = construir_calendario()
    calendario.extraer_eventos()

    # Act
    calendario.marcar_dia_sin_entrega(DIA_5, FECHA_SOLICITUD_VALIDA, motivo="Viaje de trabajo")

    # Assert
    [evento] = calendario.eventos
    assert isinstance(evento, DiaSinEntregaMarcado)
    assert evento.fecha_entrega == DIA_5
    assert evento.motivo == "Viaje de trabajo"


def test_cambio_rechazado_por_anticipacion_no_anota_eventos(
    construir_calendario, direccion_trabajo
):
    # Arrange
    calendario = construir_calendario()
    calendario.extraer_eventos()

    # Act / Assert
    with pytest.raises(AnticipacionInsuficienteError):
        calendario.cambiar_direccion_entrega(DIA_5, direccion_trabajo, date(2026, 1, 4))
    assert calendario.eventos == []


def test_cancelar_calendario_anota_solo_las_fechas_programadas_canceladas(construir_calendario):
    # Arrange
    calendario = construir_calendario(fecha_fin=date(2026, 1, 3))
    calendario.marcar_dia_sin_entrega(date(2026, 1, 2), FECHA_SOLICITUD_VALIDA)
    calendario.extraer_eventos()

    # Act
    calendario.cancelar_calendario()

    # Assert
    [evento] = calendario.eventos
    assert isinstance(evento, CalendarioEntregaCancelado)
    assert evento.fechas_canceladas == (date(2026, 1, 1), date(2026, 1, 3))


def test_completar_calendario_anota_entregas_realizadas_y_dias_sin_entrega(construir_calendario):
    # Arrange
    calendario = construir_calendario(fecha_fin=date(2026, 1, 3))
    calendario.marcar_dia_sin_entrega(date(2026, 1, 2), FECHA_SOLICITUD_VALIDA)
    calendario.entregas[0].registrar_entrega()
    calendario.extraer_eventos()

    # Act
    calendario.completar_calendario()

    # Assert
    [evento] = calendario.eventos
    assert isinstance(evento, CalendarioEntregaCompletado)
    assert evento.fecha_fin == date(2026, 1, 3)
    assert evento.entregas_realizadas == 1
    assert evento.dias_sin_entrega == 1


def test_vincular_plan_nutricional_lo_asigna_al_calendario_y_a_las_entregas_programadas(
    construir_calendario,
):
    # Arrange
    calendario = construir_calendario(fecha_fin=date(2026, 1, 2))
    calendario.marcar_dia_sin_entrega(date(2026, 1, 2), FECHA_SOLICITUD_VALIDA)
    plan_id = uuid4()

    # Act
    calendario.vincular_plan_nutricional(plan_id)

    # Assert
    assert calendario.plan_nutricional_id == plan_id
    programada, sin_entrega = calendario.entregas
    assert programada.plan_nutricional_id == plan_id
    assert sin_entrega.estado == EstadoEntrega.SIN_ENTREGA
    assert sin_entrega.plan_nutricional_id is None


def test_vincular_plan_a_calendario_inactivo_lanza_error(construir_calendario):
    # Arrange
    calendario = construir_calendario(estado=EstadoCalendario.CANCELADO)

    # Act / Assert
    with pytest.raises(CalendarioInactivoError):
        calendario.vincular_plan_nutricional(uuid4())
