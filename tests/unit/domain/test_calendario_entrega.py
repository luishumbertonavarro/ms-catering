"""Pruebas del Aggregate Root `CalendarioEntrega`.

Es el corazón del BC5. Protege, **dentro del agregado**, las reglas de las HU:

- HU-26 cambiar la dirección de un día      → `cambiar_direccion_entrega`
- HU-27 marcar un día sin entrega           → `marcar_dia_sin_entrega`
- HU-28 exigir >= 2 días de anticipación    → `_verificar_anticipacion`
- HU-30 direcciones habituales reutilizables → `registrar_direccion_habitual`
                                               + `asignar_direccion_habitual_a_dia`

Toda modificación de un día pasa por la misma cadena de guardas, **en este
orden**: calendario activo → fecha dentro del rango → anticipación → entrega
existente → entrega modificable. Los tests de "orden de validación" fijan esa
secuencia, porque determina qué error ve el paciente cuando falla más de una.
"""

from datetime import date
from uuid import uuid4

import pytest

from catering.domain.exceptions import (
    AnticipacionInsuficienteError,
    CalendarioInactivoError,
    DireccionHabitualDuplicadaError,
    DireccionHabitualNoEncontradaError,
    EntregaNoEncontradaError,
    EntregaNoModificableError,
    FechaFueraDeRangoError,
)
from catering.domain.model import (
    CalendarioEntrega,
    DiaSinEntrega,
    DireccionEntrega,
    Entrega,
    EstadoCalendario,
    EstadoEntrega,
)
from tests.conftest import FECHA_FIN, FECHA_INICIO, FECHA_SOLICITUD_VALIDA

DIA_5 = date(2026, 1, 5)

ESTADOS_INACTIVOS = [
    EstadoCalendario.CANCELADO,
    EstadoCalendario.COMPLETADO,
    EstadoCalendario.PAUSADO,
]


def _entrega_del(calendario: CalendarioEntrega, fecha: date) -> Entrega:
    return next(e for e in calendario.entregas if e.fecha == fecha)


# ---------------------------------------------------------------------------
# Factoría crear()
# ---------------------------------------------------------------------------

def test_crear_genera_una_entrega_programada_por_cada_dia_incluidos_los_extremos(
    direccion_domicilio,
):
    # Act
    calendario = CalendarioEntrega.crear(
        paciente_id=uuid4(),
        fecha_inicio=FECHA_INICIO,
        fecha_fin=FECHA_FIN,
        direccion_default=direccion_domicilio,
    )

    # Assert
    fechas = [e.fecha for e in calendario.entregas]
    assert len(fechas) == 15
    assert fechas[0] == FECHA_INICIO
    assert fechas[-1] == FECHA_FIN
    assert len(set(fechas)) == 15
    assert all(e.estado is EstadoEntrega.PROGRAMADA for e in calendario.entregas)
    assert all(e.direccion == direccion_domicilio for e in calendario.entregas)


def test_crear_deja_el_calendario_activo_y_sin_direcciones_ni_dias_sin_entrega(
    construir_calendario,
):
    # Act
    calendario = construir_calendario()

    # Assert
    assert calendario.estado is EstadoCalendario.ACTIVO
    assert calendario.direcciones_habituales == []
    assert calendario.dias_sin_entrega == []
    assert calendario.total_dias == 15


def test_crear_vincula_cada_entrega_al_calendario_y_al_plan_nutricional(construir_calendario):
    # Arrange
    plan_id = uuid4()

    # Act
    calendario = construir_calendario(plan_nutricional_id=plan_id)

    # Assert
    assert calendario.plan_nutricional_id == plan_id
    assert all(e.calendario_id == calendario.id for e in calendario.entregas)
    assert all(e.plan_nutricional_id == plan_id for e in calendario.entregas)


def test_crear_sin_plan_nutricional_deja_la_referencia_en_none(construir_calendario):
    # Act
    calendario = construir_calendario()

    # Assert
    assert calendario.plan_nutricional_id is None


def test_crear_con_inicio_igual_a_fin_genera_una_sola_entrega(construir_calendario):
    # Act
    calendario = construir_calendario(fecha_inicio=DIA_5, fecha_fin=DIA_5)

    # Assert
    assert calendario.total_dias == 1
    assert calendario.entregas[0].fecha == DIA_5


def test_crear_con_fin_anterior_al_inicio_no_lanza_error_y_genera_cero_entregas(
    construir_calendario,
):
    """Hallazgo: la factoría no valida que `fecha_fin >= fecha_inicio`.

    Devuelve un calendario ACTIVO **sin ninguna entrega**. Quien lo rechaza es la
    base de datos (`CHECK ck_calendarios_fechas`), y como ese error no tiene
    manejador HTTP, la API acaba respondiendo 500 en vez de 422. Este test fija
    el comportamiento actual; si se añade la validación al dominio, fallará y
    habrá que actualizarlo a propósito.
    """
    # Act
    calendario = construir_calendario(fecha_inicio=date(2026, 1, 15), fecha_fin=date(2026, 1, 1))

    # Assert
    assert calendario.total_dias == 0
    assert calendario.estado is EstadoCalendario.ACTIVO


def test_crear_dos_calendarios_genera_identidades_distintas(construir_calendario):
    # Act / Assert
    assert construir_calendario().id != construir_calendario().id


def test_el_constructor_rehidrata_sin_validar_ni_generar_entregas(direccion_domicilio):
    """`__init__` es la vía del repositorio: reconstruye tal cual, sin reglas.

    Por eso acepta un calendario PAUSADO con una sola entrega aunque su rango
    sea de 15 días. Es deliberado: validar aquí rompería la lectura de datos ya
    persistidos.
    """
    # Arrange
    calendario_id = uuid4()
    entrega = Entrega.crear(calendario_id, DIA_5, direccion_domicilio)

    # Act
    calendario = CalendarioEntrega(
        id=calendario_id,
        paciente_id=uuid4(),
        fecha_inicio=FECHA_INICIO,
        fecha_fin=FECHA_FIN,
        estado=EstadoCalendario.PAUSADO,
        entregas=[entrega],
        direcciones_habituales=[],
        dias_sin_entrega=[DiaSinEntrega(DIA_5, "Viaje")],
    )

    # Assert
    assert calendario.id == calendario_id
    assert calendario.estado is EstadoCalendario.PAUSADO
    assert calendario.total_dias == 1
    assert calendario.dias_sin_entrega == [DiaSinEntrega(DIA_5, "Viaje")]


# ---------------------------------------------------------------------------
# Copias defensivas
# ---------------------------------------------------------------------------

def test_modificar_la_lista_de_entregas_devuelta_no_altera_el_agregado(construir_calendario):
    # Arrange
    calendario = construir_calendario()

    # Act
    calendario.entregas.clear()

    # Assert
    assert calendario.total_dias == 15


def test_modificar_las_listas_de_direcciones_y_dias_devueltas_no_altera_el_agregado(
    construir_calendario, direccion_trabajo
):
    # Arrange
    calendario = construir_calendario()
    calendario.registrar_direccion_habitual("trabajo", direccion_trabajo)
    calendario.marcar_dia_sin_entrega(DIA_5, FECHA_SOLICITUD_VALIDA)

    # Act
    calendario.direcciones_habituales.clear()
    calendario.dias_sin_entrega.clear()

    # Assert
    assert len(calendario.direcciones_habituales) == 1
    assert len(calendario.dias_sin_entrega) == 1


# ---------------------------------------------------------------------------
# HU-26 — cambiar la dirección de un día
# ---------------------------------------------------------------------------

def test_cambiar_direccion_de_un_dia_solo_modifica_la_entrega_de_ese_dia(
    construir_calendario, direccion_domicilio, direccion_trabajo
):
    # Arrange
    calendario = construir_calendario()

    # Act
    calendario.cambiar_direccion_entrega(DIA_5, direccion_trabajo, FECHA_SOLICITUD_VALIDA)

    # Assert
    assert _entrega_del(calendario, DIA_5).direccion == direccion_trabajo
    otras = [e for e in calendario.entregas if e.fecha != DIA_5]
    assert all(e.direccion == direccion_domicilio for e in otras)
    assert _entrega_del(calendario, DIA_5).estado is EstadoEntrega.PROGRAMADA


def test_cambiar_direccion_con_exactamente_dos_dias_de_anticipacion_es_valido(
    construir_calendario, direccion_trabajo
):
    # Arrange
    calendario = construir_calendario()

    # Act — el 3 de enero para el 5 de enero: el límite exacto permitido
    calendario.cambiar_direccion_entrega(DIA_5, direccion_trabajo, date(2026, 1, 3))

    # Assert
    assert _entrega_del(calendario, DIA_5).direccion == direccion_trabajo


@pytest.mark.parametrize(
    "fecha_solicitud",
    [date(2026, 1, 4), date(2026, 1, 5), date(2026, 1, 8)],
    ids=["un_dia_antes", "mismo_dia", "despues"],
)
def test_cambiar_direccion_sin_dos_dias_de_anticipacion_lanza_error_y_no_cambia_nada(
    construir_calendario, direccion_domicilio, direccion_trabajo, fecha_solicitud
):
    # Arrange
    calendario = construir_calendario()

    # Act / Assert
    with pytest.raises(AnticipacionInsuficienteError, match="2 días de anticipación"):
        calendario.cambiar_direccion_entrega(DIA_5, direccion_trabajo, fecha_solicitud)

    assert _entrega_del(calendario, DIA_5).direccion == direccion_domicilio


@pytest.mark.parametrize(
    "fecha",
    [date(2025, 12, 31), date(2026, 1, 16)],
    ids=["antes_del_inicio", "despues_del_fin"],
)
def test_cambiar_direccion_fuera_del_rango_del_calendario_lanza_error(
    construir_calendario, direccion_trabajo, fecha
):
    # Arrange
    calendario = construir_calendario()

    # Act / Assert
    with pytest.raises(FechaFueraDeRangoError):
        calendario.cambiar_direccion_entrega(fecha, direccion_trabajo, date(2025, 12, 1))


@pytest.mark.parametrize("estado", ESTADOS_INACTIVOS, ids=lambda e: e.value)
def test_cambiar_direccion_en_un_calendario_no_activo_lanza_error(
    construir_calendario, direccion_trabajo, estado
):
    # Arrange
    calendario = construir_calendario(estado=estado)

    # Act / Assert
    with pytest.raises(CalendarioInactivoError, match=estado.value):
        calendario.cambiar_direccion_entrega(DIA_5, direccion_trabajo, FECHA_SOLICITUD_VALIDA)


def test_cambiar_direccion_de_un_dia_marcado_sin_entrega_lanza_error_no_modificable(
    construir_calendario, direccion_trabajo
):
    # Arrange
    calendario = construir_calendario()
    calendario.marcar_dia_sin_entrega(DIA_5, FECHA_SOLICITUD_VALIDA)

    # Act / Assert
    with pytest.raises(EntregaNoModificableError, match="SIN_ENTREGA"):
        calendario.cambiar_direccion_entrega(DIA_5, direccion_trabajo, FECHA_SOLICITUD_VALIDA)


def test_cambiar_direccion_de_un_dia_sin_entrega_rehidratada_lanza_entrega_no_encontrada(
    direccion_domicilio, direccion_trabajo
):
    """`EntregaNoEncontradaError` no es alcanzable con un calendario creado por la
    factoría (genera todos los días del rango). Solo aparece si el repositorio
    rehidrata un calendario al que le falta una fila de entrega."""
    # Arrange
    calendario_id = uuid4()
    calendario = CalendarioEntrega(
        id=calendario_id,
        paciente_id=uuid4(),
        fecha_inicio=FECHA_INICIO,
        fecha_fin=FECHA_FIN,
        estado=EstadoCalendario.ACTIVO,
        entregas=[Entrega.crear(calendario_id, FECHA_INICIO, direccion_domicilio)],
        direcciones_habituales=[],
        dias_sin_entrega=[],
    )

    # Act / Assert
    with pytest.raises(EntregaNoEncontradaError):
        calendario.cambiar_direccion_entrega(DIA_5, direccion_trabajo, FECHA_SOLICITUD_VALIDA)


# ---------------------------------------------------------------------------
# Orden de las guardas
# ---------------------------------------------------------------------------

def test_un_calendario_inactivo_se_reporta_antes_que_una_fecha_fuera_de_rango(
    construir_calendario, direccion_trabajo
):
    # Arrange
    calendario = construir_calendario(estado=EstadoCalendario.CANCELADO)

    # Act / Assert
    with pytest.raises(CalendarioInactivoError):
        calendario.cambiar_direccion_entrega(date(2030, 1, 1), direccion_trabajo, FECHA_SOLICITUD_VALIDA)


def test_una_fecha_fuera_de_rango_se_reporta_antes_que_la_falta_de_anticipacion(
    construir_calendario, direccion_trabajo
):
    # Arrange
    calendario = construir_calendario()

    # Act / Assert — fuera de rango Y solicitada el mismo día
    with pytest.raises(FechaFueraDeRangoError):
        calendario.cambiar_direccion_entrega(date(2026, 2, 1), direccion_trabajo, date(2026, 2, 1))


def test_la_falta_de_anticipacion_se_reporta_antes_que_una_entrega_no_modificable(
    construir_calendario, direccion_trabajo
):
    # Arrange
    calendario = construir_calendario()
    calendario.marcar_dia_sin_entrega(DIA_5, FECHA_SOLICITUD_VALIDA)

    # Act / Assert
    with pytest.raises(AnticipacionInsuficienteError):
        calendario.cambiar_direccion_entrega(DIA_5, direccion_trabajo, DIA_5)


# ---------------------------------------------------------------------------
# HU-27 — marcar un día sin entrega
# ---------------------------------------------------------------------------

def test_marcar_dia_sin_entrega_cambia_el_estado_y_registra_el_dia_con_su_motivo(
    construir_calendario,
):
    # Arrange
    calendario = construir_calendario()

    # Act
    calendario.marcar_dia_sin_entrega(DIA_5, FECHA_SOLICITUD_VALIDA, motivo="Viaje")

    # Assert
    assert _entrega_del(calendario, DIA_5).estado is EstadoEntrega.SIN_ENTREGA
    assert calendario.dias_sin_entrega == [DiaSinEntrega(fecha=DIA_5, motivo="Viaje")]
    otras = [e for e in calendario.entregas if e.fecha != DIA_5]
    assert all(e.estado is EstadoEntrega.PROGRAMADA for e in otras)


def test_marcar_dia_sin_entrega_sin_motivo_registra_el_motivo_en_none(construir_calendario):
    # Arrange
    calendario = construir_calendario()

    # Act
    calendario.marcar_dia_sin_entrega(DIA_5, FECHA_SOLICITUD_VALIDA)

    # Assert
    assert calendario.dias_sin_entrega[0].motivo is None


def test_marcar_dos_veces_el_mismo_dia_lanza_error_y_no_duplica_el_registro(
    construir_calendario,
):
    # Arrange
    calendario = construir_calendario()
    calendario.marcar_dia_sin_entrega(DIA_5, FECHA_SOLICITUD_VALIDA)

    # Act / Assert
    with pytest.raises(EntregaNoModificableError):
        calendario.marcar_dia_sin_entrega(DIA_5, FECHA_SOLICITUD_VALIDA)

    assert len(calendario.dias_sin_entrega) == 1


def test_marcar_dia_sin_entrega_sin_anticipacion_lanza_error_y_no_registra_nada(
    construir_calendario,
):
    # Arrange
    calendario = construir_calendario()

    # Act / Assert
    with pytest.raises(AnticipacionInsuficienteError):
        calendario.marcar_dia_sin_entrega(DIA_5, date(2026, 1, 4))

    assert calendario.dias_sin_entrega == []
    assert _entrega_del(calendario, DIA_5).estado is EstadoEntrega.PROGRAMADA


def test_marcar_dia_sin_entrega_fuera_del_rango_lanza_error(construir_calendario):
    # Arrange
    calendario = construir_calendario()

    # Act / Assert
    with pytest.raises(FechaFueraDeRangoError):
        calendario.marcar_dia_sin_entrega(date(2026, 1, 20), FECHA_SOLICITUD_VALIDA)


@pytest.mark.parametrize("estado", ESTADOS_INACTIVOS, ids=lambda e: e.value)
def test_marcar_dia_sin_entrega_en_un_calendario_no_activo_lanza_error(
    construir_calendario, estado
):
    # Arrange
    calendario = construir_calendario(estado=estado)

    # Act / Assert
    with pytest.raises(CalendarioInactivoError):
        calendario.marcar_dia_sin_entrega(DIA_5, FECHA_SOLICITUD_VALIDA)


# ---------------------------------------------------------------------------
# HU-30 — direcciones habituales
# ---------------------------------------------------------------------------

def test_registrar_direccion_habitual_la_vincula_al_calendario_y_al_paciente(
    construir_calendario, direccion_trabajo
):
    # Arrange
    calendario = construir_calendario()

    # Act
    calendario.registrar_direccion_habitual("trabajo", direccion_trabajo, es_principal=True)

    # Assert
    [habitual] = calendario.direcciones_habituales
    assert habitual.nombre == "trabajo"
    assert habitual.direccion == direccion_trabajo
    assert habitual.es_principal is True
    assert habitual.calendario_id == calendario.id
    assert habitual.paciente_id == calendario.paciente_id


def test_registrar_varias_direcciones_habituales_con_nombres_distintos_las_conserva_todas(
    construir_calendario, direccion_domicilio, direccion_trabajo
):
    # Arrange
    calendario = construir_calendario()

    # Act
    calendario.registrar_direccion_habitual("domicilio", direccion_domicilio)
    calendario.registrar_direccion_habitual("trabajo", direccion_trabajo)

    # Assert
    assert [d.nombre for d in calendario.direcciones_habituales] == ["domicilio", "trabajo"]


def test_registrar_una_direccion_habitual_con_nombre_repetido_lanza_error(
    construir_calendario, direccion_trabajo
):
    # Arrange
    calendario = construir_calendario()
    calendario.registrar_direccion_habitual("trabajo", direccion_trabajo)

    # Act / Assert
    with pytest.raises(DireccionHabitualDuplicadaError, match="trabajo"):
        calendario.registrar_direccion_habitual("trabajo", DireccionEntrega("Otra calle"))

    assert len(calendario.direcciones_habituales) == 1


def test_el_nombre_de_una_direccion_habitual_distingue_mayusculas(
    construir_calendario, direccion_trabajo
):
    """Documenta el comportamiento actual: "Trabajo" y "trabajo" son distintas.

    La comparación es exacta. Si se decide que deben considerarse duplicadas
    (como hace ms-plan-nutricional con los nombres de receta), este test fallará.
    """
    # Arrange
    calendario = construir_calendario()
    calendario.registrar_direccion_habitual("trabajo", direccion_trabajo)

    # Act
    calendario.registrar_direccion_habitual("Trabajo", direccion_trabajo)

    # Assert
    assert len(calendario.direcciones_habituales) == 2


def test_registrar_dos_direcciones_principales_no_lanza_error(
    construir_calendario, direccion_domicilio, direccion_trabajo
):
    """Documenta el comportamiento actual: no hay invariante de "una sola principal"."""
    # Arrange
    calendario = construir_calendario()

    # Act
    calendario.registrar_direccion_habitual("domicilio", direccion_domicilio, es_principal=True)
    calendario.registrar_direccion_habitual("trabajo", direccion_trabajo, es_principal=True)

    # Assert
    assert all(d.es_principal for d in calendario.direcciones_habituales)


def test_registrar_direccion_habitual_en_un_calendario_cancelado_esta_permitido(
    construir_calendario, direccion_trabajo
):
    """Hallazgo: es el único comando que no llama a `_verificar_activo()`.

    Todos los demás rechazan un calendario inactivo con `CalendarioInactivoError`;
    este no. Se fija el comportamiento actual para que un cambio futuro sea
    deliberado.
    """
    # Arrange
    calendario = construir_calendario(estado=EstadoCalendario.CANCELADO)

    # Act
    calendario.registrar_direccion_habitual("trabajo", direccion_trabajo)

    # Assert
    assert len(calendario.direcciones_habituales) == 1


def test_asignar_direccion_habitual_a_un_dia_le_copia_esa_direccion(
    construir_calendario, direccion_trabajo
):
    # Arrange
    calendario = construir_calendario()
    calendario.registrar_direccion_habitual("trabajo", direccion_trabajo)

    # Act
    calendario.asignar_direccion_habitual_a_dia(DIA_5, "trabajo", FECHA_SOLICITUD_VALIDA)

    # Assert
    assert _entrega_del(calendario, DIA_5).direccion == direccion_trabajo


def test_asignar_una_direccion_habitual_inexistente_lanza_error_y_no_cambia_nada(
    construir_calendario, direccion_domicilio
):
    # Arrange
    calendario = construir_calendario()

    # Act / Assert
    with pytest.raises(DireccionHabitualNoEncontradaError, match="gimnasio"):
        calendario.asignar_direccion_habitual_a_dia(DIA_5, "gimnasio", FECHA_SOLICITUD_VALIDA)

    assert _entrega_del(calendario, DIA_5).direccion == direccion_domicilio


def test_asignar_direccion_habitual_sin_anticipacion_lanza_error(
    construir_calendario, direccion_trabajo
):
    # Arrange
    calendario = construir_calendario()
    calendario.registrar_direccion_habitual("trabajo", direccion_trabajo)

    # Act / Assert
    with pytest.raises(AnticipacionInsuficienteError):
        calendario.asignar_direccion_habitual_a_dia(DIA_5, "trabajo", date(2026, 1, 4))


def test_asignar_direccion_habitual_a_un_dia_sin_entrega_lanza_error_no_modificable(
    construir_calendario, direccion_trabajo
):
    # Arrange
    calendario = construir_calendario()
    calendario.registrar_direccion_habitual("trabajo", direccion_trabajo)
    calendario.marcar_dia_sin_entrega(DIA_5, FECHA_SOLICITUD_VALIDA)

    # Act / Assert
    with pytest.raises(EntregaNoModificableError):
        calendario.asignar_direccion_habitual_a_dia(DIA_5, "trabajo", FECHA_SOLICITUD_VALIDA)


def test_la_entrega_no_modificable_se_reporta_antes_que_la_direccion_habitual_inexistente(
    construir_calendario,
):
    # Arrange
    calendario = construir_calendario()
    calendario.marcar_dia_sin_entrega(DIA_5, FECHA_SOLICITUD_VALIDA)

    # Act / Assert
    with pytest.raises(EntregaNoModificableError):
        calendario.asignar_direccion_habitual_a_dia(DIA_5, "gimnasio", FECHA_SOLICITUD_VALIDA)


@pytest.mark.parametrize("estado", ESTADOS_INACTIVOS, ids=lambda e: e.value)
def test_asignar_direccion_habitual_en_un_calendario_no_activo_lanza_error(
    construir_calendario, direccion_trabajo, estado
):
    # Arrange
    calendario = construir_calendario(estado=estado)
    calendario.registrar_direccion_habitual("trabajo", direccion_trabajo)

    # Act / Assert
    with pytest.raises(CalendarioInactivoError):
        calendario.asignar_direccion_habitual_a_dia(DIA_5, "trabajo", FECHA_SOLICITUD_VALIDA)


# ---------------------------------------------------------------------------
# Ciclo de vida del calendario
# ---------------------------------------------------------------------------

def test_completar_un_calendario_activo_lo_deja_completado_sin_tocar_las_entregas(
    construir_calendario,
):
    # Arrange
    calendario = construir_calendario()

    # Act
    calendario.completar_calendario()

    # Assert
    assert calendario.estado is EstadoCalendario.COMPLETADO
    assert all(e.estado is EstadoEntrega.PROGRAMADA for e in calendario.entregas)


def test_cancelar_un_calendario_cancela_en_cascada_solo_las_entregas_programadas(
    construir_calendario,
):
    # Arrange
    calendario = construir_calendario()
    calendario.marcar_dia_sin_entrega(DIA_5, FECHA_SOLICITUD_VALIDA)

    # Act
    calendario.cancelar_calendario()

    # Assert
    assert calendario.estado is EstadoCalendario.CANCELADO
    assert _entrega_del(calendario, DIA_5).estado is EstadoEntrega.SIN_ENTREGA
    otras = [e for e in calendario.entregas if e.fecha != DIA_5]
    assert all(e.estado is EstadoEntrega.CANCELADA for e in otras)


def test_cancelar_respeta_las_entregas_ya_entregadas(construir_calendario):
    # Arrange
    calendario = construir_calendario()
    # `registrar_entrega` no tiene comando en el agregado: se usa la entidad que
    # devuelve la copia defensiva, que comparte las mismas instancias de Entrega.
    _entrega_del(calendario, FECHA_INICIO).registrar_entrega()

    # Act
    calendario.cancelar_calendario()

    # Assert
    assert _entrega_del(calendario, FECHA_INICIO).estado is EstadoEntrega.ENTREGADA


@pytest.mark.parametrize("estado", ESTADOS_INACTIVOS, ids=lambda e: e.value)
def test_cancelar_un_calendario_no_activo_lanza_error(construir_calendario, estado):
    # Arrange
    calendario = construir_calendario(estado=estado)

    # Act / Assert
    with pytest.raises(CalendarioInactivoError):
        calendario.cancelar_calendario()

    assert calendario.estado is estado


@pytest.mark.parametrize("estado", ESTADOS_INACTIVOS, ids=lambda e: e.value)
def test_completar_un_calendario_no_activo_lanza_error(construir_calendario, estado):
    # Arrange
    calendario = construir_calendario(estado=estado)

    # Act / Assert
    with pytest.raises(CalendarioInactivoError):
        calendario.completar_calendario()

    assert calendario.estado is estado
