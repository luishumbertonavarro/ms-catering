"""Pruebas del servicio de dominio `ValidadorCambioCalendarioService`.

Responde, sin tocar ningún calendario, a la pregunta que la app del paciente
hace antes de mostrar el botón "cambiar" (HU-28): ¿todavía se puede modificar la
entrega de esa fecha? Y si no, ¿cuántos días faltaron?

Es Python puro sobre `AnticipacionMinima`: se prueba sin dobles.
"""

from datetime import date

import pytest

from catering.domain.services import ValidadorCambioCalendarioService

FECHA_ENTREGA = date(2026, 1, 10)


@pytest.fixture
def validador() -> ValidadorCambioCalendarioService:
    return ValidadorCambioCalendarioService()


@pytest.mark.parametrize(
    ("fecha_solicitud", "esperado"),
    [
        (date(2026, 1, 1), True),
        (date(2026, 1, 8), True),
        (date(2026, 1, 9), False),
        (date(2026, 1, 10), False),
    ],
    ids=["9_dias", "2_dias_limite", "1_dia", "mismo_dia"],
)
def test_puede_modificar_aplica_la_regla_de_los_dos_dias(validador, fecha_solicitud, esperado):
    # Act
    resultado = validador.puede_modificar(FECHA_ENTREGA, fecha_solicitud)

    # Assert
    assert resultado is esperado


@pytest.mark.parametrize(
    ("fecha_solicitud", "dias_faltantes"),
    [
        (date(2026, 1, 1), 0),   # sobra anticipación
        (date(2026, 1, 8), 0),   # justo en el límite
        (date(2026, 1, 9), 1),   # faltó un día
        (date(2026, 1, 10), 2),  # el mismo día: faltaron los dos
    ],
    ids=["sobra", "limite", "falta_1", "falta_2"],
)
def test_dias_restantes_para_modificar_devuelve_lo_que_falto_de_anticipacion(
    validador, fecha_solicitud, dias_faltantes
):
    # Act
    resultado = validador.dias_restantes_para_modificar(FECHA_ENTREGA, fecha_solicitud)

    # Assert
    assert resultado == dias_faltantes


def test_dias_restantes_con_la_entrega_ya_pasada_crece_por_encima_de_dos(validador):
    """Documenta el comportamiento actual: con una solicitud posterior a la
    entrega, `max(0, 2 - delta)` supera el mínimo (aquí, 2 - (-3) = 5).

    Matemáticamente es coherente ("faltaron 5 días"), pero el cliente no debería
    interpretarlo como "espera 5 días": esa entrega ya no se puede modificar nunca.
    """
    # Act
    resultado = validador.dias_restantes_para_modificar(FECHA_ENTREGA, date(2026, 1, 13))

    # Assert
    assert resultado == 5
    assert validador.puede_modificar(FECHA_ENTREGA, date(2026, 1, 13)) is False


def test_puede_modificar_y_dias_restantes_son_coherentes_entre_si(validador):
    # Arrange — se recorre un mes entero de fechas de solicitud
    solicitudes = [date(2026, 1, d) for d in range(1, 31)]

    # Act / Assert — "puede" si y solo si "no falta ningún día"
    for solicitud in solicitudes:
        puede = validador.puede_modificar(FECHA_ENTREGA, solicitud)
        faltan = validador.dias_restantes_para_modificar(FECHA_ENTREGA, solicitud)
        assert puede is (faltan == 0), solicitud
