"""Pruebas de la entidad `Entrega` y de `DireccionHabitual`.

`Entrega` es una entidad hija del agregado `CalendarioEntrega`. Sus métodos
(`cambiar_direccion`, `marcar_sin_entrega`, `cancelar`, `registrar_entrega`) son
mutaciones directas: **no validan transiciones**. Quien protege las reglas
(anticipación, estado modificable, calendario activo) es el agregado. Estos tests
fijan ese reparto de responsabilidades.
"""

from datetime import date
from uuid import uuid4

import pytest

from catering.domain.model import (
    DireccionEntrega,
    DireccionHabitual,
    Entrega,
    EstadoEntrega,
    Etiqueta,
)


@pytest.fixture
def entrega(direccion_domicilio) -> Entrega:
    return Entrega.crear(
        calendario_id=uuid4(),
        fecha=date(2026, 1, 5),
        direccion=direccion_domicilio,
    )


# ---------------------------------------------------------------------------
# Creación
# ---------------------------------------------------------------------------

def test_crear_una_entrega_nace_programada_y_sin_etiqueta(direccion_domicilio):
    # Arrange
    calendario_id = uuid4()

    # Act
    entrega = Entrega.crear(
        calendario_id=calendario_id,
        fecha=date(2026, 1, 5),
        direccion=direccion_domicilio,
    )

    # Assert
    assert entrega.calendario_id == calendario_id
    assert entrega.fecha == date(2026, 1, 5)
    assert entrega.estado is EstadoEntrega.PROGRAMADA
    assert entrega.direccion == direccion_domicilio
    assert entrega.plan_nutricional_id is None
    assert entrega.etiqueta is None
    assert entrega.tiene_etiqueta is False


def test_crear_una_entrega_con_plan_nutricional_conserva_la_referencia(direccion_domicilio):
    # Arrange
    plan_id = uuid4()

    # Act
    entrega = Entrega.crear(uuid4(), date(2026, 1, 5), direccion_domicilio, plan_nutricional_id=plan_id)

    # Assert
    assert entrega.plan_nutricional_id == plan_id


def test_crear_dos_entregas_genera_identidades_distintas(direccion_domicilio):
    # Arrange
    calendario_id = uuid4()

    # Act
    una = Entrega.crear(calendario_id, date(2026, 1, 5), direccion_domicilio)
    otra = Entrega.crear(calendario_id, date(2026, 1, 5), direccion_domicilio)

    # Assert
    assert una.id != otra.id


# ---------------------------------------------------------------------------
# Estado modificable
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("estado", "esperado"),
    [
        (EstadoEntrega.PROGRAMADA, True),
        (EstadoEntrega.SIN_ENTREGA, False),
        (EstadoEntrega.CANCELADA, False),
        (EstadoEntrega.ENTREGADA, False),
    ],
)
def test_es_modificable_solo_es_verdadero_para_una_entrega_programada(entrega, estado, esperado):
    # Arrange
    entrega.estado = estado

    # Act / Assert
    assert entrega.es_modificable is esperado


# ---------------------------------------------------------------------------
# Mutaciones
# ---------------------------------------------------------------------------

def test_cambiar_direccion_reemplaza_la_direccion_de_la_entrega(entrega, direccion_trabajo):
    # Act
    entrega.cambiar_direccion(direccion_trabajo)

    # Assert
    assert entrega.direccion == direccion_trabajo
    assert entrega.estado is EstadoEntrega.PROGRAMADA


def test_marcar_sin_entrega_deja_la_entrega_en_estado_sin_entrega(entrega):
    # Act
    entrega.marcar_sin_entrega()

    # Assert
    assert entrega.estado is EstadoEntrega.SIN_ENTREGA
    assert entrega.es_modificable is False


def test_cancelar_deja_la_entrega_en_estado_cancelada(entrega):
    # Act
    entrega.cancelar()

    # Assert
    assert entrega.estado is EstadoEntrega.CANCELADA


def test_registrar_entrega_deja_la_entrega_en_estado_entregada(entrega):
    # Act
    entrega.registrar_entrega()

    # Assert
    assert entrega.estado is EstadoEntrega.ENTREGADA


def test_una_entrega_cancelada_puede_marcarse_entregada_porque_la_entidad_no_valida(entrega):
    """Documenta el comportamiento actual: la entidad no protege sus transiciones.

    Hoy no es un problema porque `CalendarioEntrega` comprueba `es_modificable`
    antes de mutar, y `registrar_entrega` no está expuesto en la API. Si se
    expone (p. ej. desde ms-logistica-entrega), la validación deberá añadirse en
    el agregado o en la entidad, y este test fallará a propósito.
    """
    # Arrange
    entrega.cancelar()

    # Act
    entrega.registrar_entrega()

    # Assert
    assert entrega.estado is EstadoEntrega.ENTREGADA


def test_una_entrega_con_etiqueta_indica_que_tiene_etiqueta(entrega):
    # Arrange
    entrega.etiqueta = Etiqueta("María", "PAC-1", "Av. Banzer 123", date(2026, 1, 5), "123")

    # Act / Assert
    assert entrega.tiene_etiqueta is True


# ---------------------------------------------------------------------------
# DireccionHabitual
# ---------------------------------------------------------------------------

def test_crear_una_direccion_habitual_conserva_sus_datos_y_no_es_principal(direccion_trabajo):
    # Arrange
    calendario_id, paciente_id = uuid4(), uuid4()

    # Act
    habitual = DireccionHabitual.crear(
        calendario_id=calendario_id,
        paciente_id=paciente_id,
        nombre="trabajo",
        direccion=direccion_trabajo,
    )

    # Assert
    assert habitual.calendario_id == calendario_id
    assert habitual.paciente_id == paciente_id
    assert habitual.nombre == "trabajo"
    assert habitual.direccion == direccion_trabajo
    assert habitual.es_principal is False


def test_crear_una_direccion_habitual_principal_la_marca_como_principal():
    # Act
    habitual = DireccionHabitual.crear(
        uuid4(), uuid4(), "domicilio", DireccionEntrega("Av. 1"), es_principal=True
    )

    # Assert
    assert habitual.es_principal is True


def test_crear_dos_direcciones_habituales_genera_identidades_distintas():
    # Arrange
    direccion = DireccionEntrega("Av. 1")

    # Act
    una = DireccionHabitual.crear(uuid4(), uuid4(), "a", direccion)
    otra = DireccionHabitual.crear(uuid4(), uuid4(), "a", direccion)

    # Assert
    assert una.id != otra.id
