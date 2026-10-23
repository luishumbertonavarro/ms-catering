"""Pruebas del mapper dominio → esquema de respuesta.

`presentation/api/schemas/mappers.py` contiene `calendario_to_response`, una
**función pura**: recibe el agregado y devuelve un modelo Pydantic. No usa
`Request`, ni sesión de base de datos, ni cliente HTTP, así que se prueba como
cualquier otra función del dominio — sin dobles y sin levantar nada.

Lo que verifican estos tests es el trabajo real del mapper: **aplanar el value
object** `DireccionEntrega` en `direccion`/`referencia`/`zona`, convertir los
enums a su valor de texto y **recorrer** entregas y direcciones habituales.
"""

from datetime import date
from uuid import uuid4

from catering.domain.model import DireccionEntrega, Etiqueta
from catering.presentation.api.schemas import CalendarioResponse, calendario_to_response
from tests.conftest import FECHA_SOLICITUD_VALIDA


def test_mapear_un_calendario_copia_su_cabecera_y_convierte_el_estado_a_texto(
    construir_calendario,
):
    # Arrange
    plan_id = uuid4()
    calendario = construir_calendario(plan_nutricional_id=plan_id)

    # Act
    respuesta = calendario_to_response(calendario)

    # Assert
    assert isinstance(respuesta, CalendarioResponse)
    assert respuesta.id == calendario.id
    assert respuesta.paciente_id == calendario.paciente_id
    assert respuesta.fecha_inicio == date(2026, 1, 1)
    assert respuesta.fecha_fin == date(2026, 1, 15)
    assert respuesta.estado == "ACTIVO"
    assert respuesta.total_dias == 15
    assert respuesta.plan_nutricional_id == plan_id


def test_mapear_un_calendario_aplana_la_direccion_de_cada_entrega(construir_calendario):
    # Arrange
    calendario = construir_calendario()

    # Act
    respuesta = calendario_to_response(calendario)

    # Assert
    assert len(respuesta.entregas) == 15
    primera = respuesta.entregas[0]
    assert primera.id == calendario.entregas[0].id
    assert primera.fecha == date(2026, 1, 1)
    assert primera.estado == "PROGRAMADA"
    assert primera.direccion == "Av. Banzer 123"
    assert primera.referencia == "Portón verde"
    assert primera.zona == "Equipetrol"
    assert primera.tiene_etiqueta is False


def test_mapear_un_calendario_refleja_el_estado_de_cada_entrega(construir_calendario):
    # Arrange
    calendario = construir_calendario()
    calendario.marcar_dia_sin_entrega(date(2026, 1, 5), FECHA_SOLICITUD_VALIDA)

    # Act
    respuesta = calendario_to_response(calendario)

    # Assert
    estados = {e.fecha: e.estado for e in respuesta.entregas}
    assert estados[date(2026, 1, 5)] == "SIN_ENTREGA"
    assert estados[date(2026, 1, 6)] == "PROGRAMADA"


def test_mapear_una_entrega_con_etiqueta_marca_tiene_etiqueta(construir_calendario):
    # Arrange
    calendario = construir_calendario()
    calendario.entregas[0].etiqueta = Etiqueta("María", "PAC-1", "Av. 1", date(2026, 1, 1), "123")

    # Act
    respuesta = calendario_to_response(calendario)

    # Assert
    assert respuesta.entregas[0].tiene_etiqueta is True
    assert respuesta.entregas[1].tiene_etiqueta is False


def test_mapear_un_calendario_incluye_sus_direcciones_habituales_aplanadas(
    construir_calendario, direccion_trabajo
):
    # Arrange
    calendario = construir_calendario()
    calendario.registrar_direccion_habitual("trabajo", direccion_trabajo, es_principal=True)

    # Act
    respuesta = calendario_to_response(calendario)

    # Assert
    [habitual] = respuesta.direcciones_habituales
    assert habitual.id == calendario.direcciones_habituales[0].id
    assert habitual.nombre == "trabajo"
    assert habitual.direccion == "Calle Libertad 456, piso 3"
    assert habitual.referencia == "Oficina 3B"
    assert habitual.zona == "Centro"
    assert habitual.es_principal is True


def test_mapear_un_calendario_sin_plan_ni_direcciones_deja_none_y_lista_vacia(
    construir_calendario,
):
    # Arrange
    calendario = construir_calendario()

    # Act
    respuesta = calendario_to_response(calendario)

    # Assert
    assert respuesta.plan_nutricional_id is None
    assert respuesta.direcciones_habituales == []


def test_mapear_una_entrega_sin_referencia_ni_zona_deja_esos_campos_en_none(
    construir_calendario,
):
    # Arrange
    calendario = construir_calendario()
    calendario.cambiar_direccion_entrega(
        date(2026, 1, 3), DireccionEntrega(direccion="Solo calle"), FECHA_SOLICITUD_VALIDA
    )

    # Act
    respuesta = calendario_to_response(calendario)

    # Assert
    entrega = next(e for e in respuesta.entregas if e.fecha == date(2026, 1, 3))
    assert entrega.direccion == "Solo calle"
    assert entrega.referencia is None
    assert entrega.zona is None


def test_el_mapeo_no_expone_los_dias_sin_entrega_ni_las_coordenadas(construir_calendario):
    """Documenta el contrato actual de la respuesta.

    `dias_sin_entrega` (con su motivo) y `latitud`/`longitud` existen en el
    dominio y en la base, pero `CalendarioResponse` no los publica. El estado
    `SIN_ENTREGA` de la entrega sí llega; el motivo, no.
    """
    # Arrange
    calendario = construir_calendario()
    calendario.marcar_dia_sin_entrega(date(2026, 1, 5), FECHA_SOLICITUD_VALIDA, motivo="Viaje")

    # Act
    campos = set(calendario_to_response(calendario).model_dump())
    campos_entrega = set(calendario_to_response(calendario).entregas[0].model_dump())

    # Assert
    assert "dias_sin_entrega" not in campos
    assert {"latitud", "longitud"}.isdisjoint(campos_entrega)
