"""Pruebas de las funciones de mapeo dominio ↔ ORM del repositorio.

`calendario_repository_impl.py` tiene dos mitades:

1. **Funciones de mapeo** (`_entrega_to_orm`, `_calendario_from_orm`, …): reciben
   un objeto y devuelven otro. Construir una instancia de un modelo ORM en memoria
   **no abre ninguna sesión ni ejecuta SQL**, así que son funciones puras y se
   prueban aquí.
2. **Los métodos del repositorio** (`guardar`, `obtener_por_id`, …): ejecutan SQL
   contra PostgreSQL. Esos **no** se prueban aquí — nada de doblar `AsyncSession`
   ni simular resultados de SQLAlchemy —; los cubre `tests/integration/`.

La frontera la decide el I/O, no la capa.
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4

from catering.domain.model import (
    DiaSinEntrega,
    DireccionEntrega,
    DireccionHabitual,
    Entrega,
    EstadoCalendario,
    EstadoEntrega,
    Etiqueta,
)
from catering.infrastructure.persistence.calendario_repository_impl import (
    _calendario_from_orm,
    _dir_habitual_from_orm,
    _dir_habitual_to_orm,
    _direccion_from_orm,
    _entrega_from_orm,
    _entrega_to_orm,
)
from catering.infrastructure.persistence.orm_models import (
    CalendarioEntregaORM,
    DiaSinEntregaORM,
    DireccionHabitualORM,
    EntregaORM,
)

GEOLOCALIZADA = DireccionEntrega(
    direccion="Av. Banzer 123",
    referencia="Portón verde",
    zona="Equipetrol",
    latitud=Decimal("-17.7833000"),
    longitud=Decimal("-63.1821000"),
)


def _entrega(**cambios) -> Entrega:
    valores = {
        "id": uuid4(),
        "calendario_id": uuid4(),
        "fecha": date(2026, 1, 5),
        "estado": EstadoEntrega.PROGRAMADA,
        "direccion": GEOLOCALIZADA,
        "plan_nutricional_id": uuid4(),
    }
    valores.update(cambios)
    return Entrega(**valores)


# ---------------------------------------------------------------------------
# Entrega
# ---------------------------------------------------------------------------

def test_una_entrega_pasa_al_orm_y_vuelve_al_dominio_sin_perder_datos():
    # Arrange
    entrega = _entrega(estado=EstadoEntrega.SIN_ENTREGA)

    # Act
    reconstruida = _entrega_from_orm(_entrega_to_orm(entrega))

    # Assert — `Entrega` es dataclass: compara campo a campo
    assert reconstruida == entrega


def test_una_entrega_guarda_su_estado_en_el_orm_como_texto():
    # Act
    fila = _entrega_to_orm(_entrega(estado=EstadoEntrega.CANCELADA))

    # Assert — la columna es String(20) con un CHECK sobre los valores del enum
    assert fila.estado == "CANCELADA"


def test_una_entrega_sin_coordenadas_deja_latitud_y_longitud_en_null():
    # Arrange
    entrega = _entrega(direccion=DireccionEntrega(direccion="Solo calle"))

    # Act
    fila = _entrega_to_orm(entrega)

    # Assert
    assert fila.latitud is None
    assert fila.longitud is None
    assert _entrega_from_orm(fila).direccion == DireccionEntrega(direccion="Solo calle")


def test_las_coordenadas_vuelven_del_orm_como_decimal():
    """La columna es `Numeric`, pero el ORM la anota como `float`: el mapeo
    convierte a `Decimal` pasando por `str` para no arrastrar error binario."""
    # Arrange
    fila = _entrega_to_orm(_entrega())
    fila.latitud = -17.7833  # lo que devolvería el driver tras un float

    # Act
    direccion = _direccion_from_orm(fila)

    # Assert
    assert direccion.latitud == Decimal("-17.7833")
    assert isinstance(direccion.longitud, Decimal)


def test_la_etiqueta_se_escribe_en_el_orm_pero_no_se_reconstruye_al_leer():
    """Hallazgo: la `Etiqueta` se pierde en el viaje de ida y vuelta.

    `_entrega_to_orm` copia tres de sus campos a las columnas `etiqueta_*`, pero
    `_entrega_from_orm` nunca la reconstruye: tras leer de la base,
    `tiene_etiqueta` es siempre `False`. Además, `direccion_entrega` y
    `fecha_entrega` de la etiqueta ni siquiera tienen columna. Hoy no hay ningún
    caso de uso que asigne etiquetas (HU-35 es de ms-produccion-cocina), así que
    no se modificó `src/`; este test fija el comportamiento actual.
    """
    # Arrange
    entrega = _entrega(
        etiqueta=Etiqueta("María Pérez", "PAC-0001", "Av. Banzer 123", date(2026, 1, 5), "1234567")
    )

    # Act
    fila = _entrega_to_orm(entrega)
    reconstruida = _entrega_from_orm(fila)

    # Assert
    assert fila.etiqueta_nombre_paciente == "María Pérez"
    assert fila.etiqueta_codigo_paciente == "PAC-0001"
    assert fila.etiqueta_numero_id == "1234567"
    assert reconstruida.etiqueta is None
    assert reconstruida.tiene_etiqueta is False


# ---------------------------------------------------------------------------
# DireccionHabitual
# ---------------------------------------------------------------------------

def test_una_direccion_habitual_pasa_al_orm_y_vuelve_al_dominio_sin_perder_datos():
    # Arrange
    habitual = DireccionHabitual(
        id=uuid4(),
        calendario_id=uuid4(),
        paciente_id=uuid4(),
        nombre="trabajo",
        direccion=GEOLOCALIZADA,
        es_principal=True,
    )

    # Act
    reconstruida = _dir_habitual_from_orm(_dir_habitual_to_orm(habitual))

    # Assert
    assert reconstruida == habitual


# ---------------------------------------------------------------------------
# CalendarioEntrega
# ---------------------------------------------------------------------------

def test_un_calendario_se_reconstruye_desde_el_orm_con_toda_su_jerarquia():
    # Arrange — una fila de calendario con sus tres colecciones hijas, en memoria
    calendario_id, paciente_id, plan_id = uuid4(), uuid4(), uuid4()
    entrega = _entrega(calendario_id=calendario_id)
    habitual = DireccionHabitual(uuid4(), calendario_id, paciente_id, "trabajo", GEOLOCALIZADA)
    fila = CalendarioEntregaORM(
        id=calendario_id,
        paciente_id=paciente_id,
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 1, 15),
        estado="ACTIVO",
        plan_nutricional_id=plan_id,
        entregas=[_entrega_to_orm(entrega)],
        direcciones_habituales=[_dir_habitual_to_orm(habitual)],
        dias_sin_entrega=[
            DiaSinEntregaORM(id=uuid4(), calendario_id=calendario_id, fecha=date(2026, 1, 7), motivo="Viaje")
        ],
    )

    # Act
    calendario = _calendario_from_orm(fila)

    # Assert
    assert calendario.id == calendario_id
    assert calendario.paciente_id == paciente_id
    assert calendario.estado is EstadoCalendario.ACTIVO
    assert calendario.plan_nutricional_id == plan_id
    assert calendario.entregas == [entrega]
    assert calendario.direcciones_habituales == [habitual]
    assert calendario.dias_sin_entrega == [DiaSinEntrega(date(2026, 1, 7), "Viaje")]


def test_un_calendario_sin_colecciones_se_reconstruye_con_listas_vacias():
    # Arrange
    fila = CalendarioEntregaORM(
        id=uuid4(),
        paciente_id=uuid4(),
        fecha_inicio=date(2026, 1, 1),
        fecha_fin=date(2026, 1, 15),
        estado="CANCELADO",
        plan_nutricional_id=None,
    )

    # Act
    calendario = _calendario_from_orm(fila)

    # Assert
    assert calendario.estado is EstadoCalendario.CANCELADO
    assert calendario.entregas == []
    assert calendario.direcciones_habituales == []
    assert calendario.dias_sin_entrega == []
    assert calendario.plan_nutricional_id is None


def test_los_modelos_orm_declaran_las_restricciones_que_protegen_los_datos():
    """El esquema es la última línea de defensa: lo que el dominio no valida
    (p. ej. `fecha_fin >= fecha_inicio`) lo rechaza la base."""
    # Arrange
    restricciones = {
        c.name
        for tabla in (CalendarioEntregaORM, EntregaORM, DireccionHabitualORM, DiaSinEntregaORM)
        for c in tabla.__table__.constraints
        if c.name
    }

    # Act / Assert
    assert {
        "ck_calendarios_estado",
        "ck_calendarios_fechas",
        "ck_entregas_estado",
        "uq_direcciones_calendario_nombre",
        "uq_dias_sin_entrega_fecha",
    } <= restricciones


def test_las_colecciones_del_agregado_prohiben_la_carga_perezosa_implicita():
    """Regresión del hallazgo corregido (ver tests/README.md §8).

    Con `AsyncSession`, una carga perezosa no puede hacer I/O: antes de la
    corrección, `guardar()` releía el calendario sin sus colecciones y todo
    comando de modificación terminaba en 500 (`MissingGreenlet`). `lazy="raise"`
    convierte cualquier olvido futuro en un error explícito, y `_EAGER` es la
    única vía de carga.
    """
    # Arrange
    colecciones = (
        CalendarioEntregaORM.entregas,
        CalendarioEntregaORM.direcciones_habituales,
        CalendarioEntregaORM.dias_sin_entrega,
    )

    # Act / Assert
    for coleccion in colecciones:
        assert coleccion.property.lazy == "raise", coleccion
