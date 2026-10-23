"""Pruebas del repositorio en memoria `InMemoryCalendarioRepository`.

Es una implementación del puerto `CalendarioEntregaRepository` sin base de datos,
pensada para desarrollo. Se prueba como unitaria porque no hace I/O: guarda los
agregados en un `dict` de módulo.

Ese `dict` es **global** (`_store`), compartido por todas las instancias y por
todos los tests de la sesión. Por eso aquí, igual que en integración, ningún
test asume que el almacén está vacío: se comprueba **pertenencia** con ids
generados en el propio test.
"""

from datetime import date
from uuid import uuid4

from catering.domain.model import EstadoCalendario
from catering.domain.repositories import CalendarioEntregaRepository
from catering.infrastructure.persistence import InMemoryCalendarioRepository
from tests.conftest import FECHA_SOLICITUD_VALIDA


def test_el_repositorio_en_memoria_implementa_el_puerto_del_dominio():
    # Act / Assert
    assert isinstance(InMemoryCalendarioRepository(), CalendarioEntregaRepository)


async def test_guardar_y_obtener_por_id_devuelve_el_mismo_agregado(construir_calendario):
    # Arrange
    repo = InMemoryCalendarioRepository()
    calendario = construir_calendario()

    # Act
    await repo.guardar(calendario)
    recuperado = await repo.obtener_por_id(calendario.id)

    # Assert
    assert recuperado is calendario


async def test_obtener_por_id_inexistente_devuelve_none():
    # Act / Assert
    assert await InMemoryCalendarioRepository().obtener_por_id(uuid4()) is None


async def test_obtener_por_paciente_devuelve_solo_un_calendario_activo(construir_calendario):
    # Arrange
    repo = InMemoryCalendarioRepository()
    activo = construir_calendario()
    await repo.guardar(activo)

    # Act
    recuperado = await repo.obtener_por_paciente(activo.paciente_id)

    # Assert
    assert recuperado is activo


async def test_obtener_por_paciente_ignora_un_calendario_cancelado(construir_calendario):
    # Arrange
    repo = InMemoryCalendarioRepository()
    cancelado = construir_calendario(estado=EstadoCalendario.CANCELADO)
    await repo.guardar(cancelado)

    # Act / Assert
    assert await repo.obtener_por_paciente(cancelado.paciente_id) is None


async def test_listar_activos_incluye_los_activos_y_excluye_los_cancelados(construir_calendario):
    # Arrange
    repo = InMemoryCalendarioRepository()
    activo = construir_calendario()
    cancelado = construir_calendario(estado=EstadoCalendario.CANCELADO)
    await repo.guardar(activo)
    await repo.guardar(cancelado)

    # Act
    ids = {c.id for c in await repo.listar_activos()}

    # Assert — pertenencia, no igualdad: el almacén es compartido
    assert activo.id in ids
    assert cancelado.id not in ids


async def test_listar_con_entregas_en_fecha_solo_considera_entregas_programadas(
    construir_calendario,
):
    # Arrange
    repo = InMemoryCalendarioRepository()
    con_entrega = construir_calendario()
    sin_entrega_ese_dia = construir_calendario()
    sin_entrega_ese_dia.marcar_dia_sin_entrega(date(2026, 1, 5), FECHA_SOLICITUD_VALIDA)
    fuera_de_rango = construir_calendario(fecha_inicio=date(2026, 2, 1), fecha_fin=date(2026, 2, 15))
    for calendario in (con_entrega, sin_entrega_ese_dia, fuera_de_rango):
        await repo.guardar(calendario)

    # Act
    ids = {c.id for c in await repo.listar_con_entregas_en_fecha(date(2026, 1, 5))}

    # Assert
    assert con_entrega.id in ids
    assert sin_entrega_ese_dia.id not in ids
    assert fuera_de_rango.id not in ids


async def test_dos_instancias_del_repositorio_en_memoria_comparten_el_almacen(
    construir_calendario,
):
    """Documenta el comportamiento actual: `_store` es una variable de módulo.

    Lo que guarda una instancia lo ve cualquier otra. Es cómodo para desarrollo
    (sobrevive entre peticiones), pero hace que los tests que lo usen no estén
    aislados entre sí.
    """
    # Arrange
    calendario = construir_calendario()
    await InMemoryCalendarioRepository().guardar(calendario)

    # Act
    recuperado = await InMemoryCalendarioRepository().obtener_por_id(calendario.id)

    # Assert
    assert recuperado is calendario
