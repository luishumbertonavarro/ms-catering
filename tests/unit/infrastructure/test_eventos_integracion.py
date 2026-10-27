"""Los payloads respetan los contratos de Eventos_Integracion_NUR-TRICENTER.docx (sección 4)."""
from datetime import date
from uuid import uuid4

from catering.infrastructure.messaging.eventos_integracion import a_mensaje
from tests.conftest import FECHA_SOLICITUD_VALIDA

DIRECCION_DOMICILIO = {
    "direccion": "Av. Banzer 123",
    "referencia": "Portón verde",
    "zona": "Equipetrol",
    "latitud": None,
    "longitud": None,
}


def _unico_mensaje(calendario):
    [evento] = calendario.extraer_eventos()
    return a_mensaje(evento, calendario)


def test_calendario_creado_se_publica_en_calendario_creado_con_el_contrato(construir_calendario):
    # Arrange
    plan_id = uuid4()
    calendario = construir_calendario(plan_nutricional_id=plan_id)

    # Act
    mensaje = _unico_mensaje(calendario)

    # Assert
    assert mensaje.tipo == "CalendarioEntregaCreado"
    assert mensaje.routing_key == "calendario.creado"
    assert mensaje.payload == {
        "calendario_id": str(calendario.id),
        "paciente_id": str(calendario.paciente_id),
        "plan_nutricional_id": str(plan_id),
        "fecha_inicio": "2026-01-01",
        "fecha_fin": "2026-01-15",
        "total_dias": 15,
        "direccion_entrega": DIRECCION_DOMICILIO,
    }


def test_direccion_cambiada_lleva_la_direccion_anterior_y_la_nueva(
    construir_calendario, direccion_trabajo
):
    # Arrange
    calendario = construir_calendario()
    calendario.extraer_eventos()
    calendario.cambiar_direccion_entrega(date(2026, 1, 6), direccion_trabajo, FECHA_SOLICITUD_VALIDA)
    entrega = calendario.entregas[5]

    # Act
    mensaje = _unico_mensaje(calendario)

    # Assert
    assert mensaje.routing_key == "direccion_entrega.cambiada"
    assert mensaje.payload == {
        "calendario_id": str(calendario.id),
        "entrega_id": str(entrega.id),
        "paciente_id": str(calendario.paciente_id),
        "fecha_entrega": "2026-01-06",
        "origen": "MANUAL",
        "nombre_direccion_habitual": None,
        "direccion_anterior": DIRECCION_DOMICILIO,
        "direccion_nueva": {
            "direccion": "Calle Libertad 456, piso 3",
            "referencia": "Oficina 3B",
            "zona": "Centro",
            "latitud": None,
            "longitud": None,
        },
    }


def test_dia_sin_entrega_se_publica_con_su_motivo(construir_calendario):
    # Arrange
    calendario = construir_calendario()
    calendario.extraer_eventos()
    calendario.marcar_dia_sin_entrega(date(2026, 1, 10), FECHA_SOLICITUD_VALIDA, "Viaje de trabajo")

    # Act
    mensaje = _unico_mensaje(calendario)

    # Assert
    assert mensaje.routing_key == "dia_sin_entrega.marcado"
    assert mensaje.payload["fecha_entrega"] == "2026-01-10"
    assert mensaje.payload["motivo"] == "Viaje de trabajo"
    assert mensaje.payload["entrega_id"] == str(calendario.entregas[9].id)


def test_calendario_cancelado_se_publica_con_las_fechas_canceladas(construir_calendario):
    # Arrange
    calendario = construir_calendario(fecha_fin=date(2026, 1, 2))
    calendario.extraer_eventos()
    calendario.cancelar_calendario()

    # Act
    mensaje = _unico_mensaje(calendario)

    # Assert
    assert mensaje.routing_key == "calendario.cancelado"
    assert mensaje.payload == {
        "calendario_id": str(calendario.id),
        "paciente_id": str(calendario.paciente_id),
        "fechas_canceladas": ["2026-01-01", "2026-01-02"],
    }


def test_calendario_completado_se_publica_con_su_resumen(construir_calendario):
    # Arrange
    calendario = construir_calendario()
    calendario.extraer_eventos()
    calendario.completar_calendario()

    # Act
    mensaje = _unico_mensaje(calendario)

    # Assert
    assert mensaje.routing_key == "calendario.completado"
    assert mensaje.payload["fecha_fin"] == "2026-01-15"
    assert mensaje.payload["entregas_realizadas"] == 0
    assert mensaje.payload["dias_sin_entrega"] == 0
