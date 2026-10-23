"""Pruebas de los query handlers (lado de lectura de CQRS).

Los handlers de lectura no aplican reglas: delegan en el repositorio y devuelven
lo que este responda. Por eso cada test verifica dos cosas — que se llamó al
método correcto del puerto con el argumento correcto, y que el resultado se
devuelve sin transformar — y que **nunca** se escribe nada.

`VerificarPuedeModificarHandler` es la excepción: no usa el repositorio, sino el
servicio de dominio `ValidadorCambioCalendarioService`.
"""

from datetime import date
from unittest.mock import Mock
from uuid import uuid4

from catering.application.queries import (
    ListarCalendariosActivosQuery,
    ObtenerCalendarioPacienteQuery,
    ObtenerCalendarioPorIdQuery,
    ObtenerEntregasDeFechaQuery,
    VerificarPuedeModificarQuery,
)
from catering.application.use_cases import (
    ListarCalendariosActivosHandler,
    ObtenerCalendarioPacienteHandler,
    ObtenerCalendarioPorIdHandler,
    ObtenerEntregasDeFechaHandler,
    VerificarPuedeModificarHandler,
)
from catering.domain.services import ValidadorCambioCalendarioService


async def test_obtener_calendario_por_id_devuelve_lo_que_responde_el_repositorio(
    calendario_repo_mock, construir_calendario
):
    # Arrange
    calendario = construir_calendario()
    calendario_repo_mock.obtener_por_id.return_value = calendario
    handler = ObtenerCalendarioPorIdHandler(calendario_repo_mock)

    # Act
    resultado = await handler.ejecutar(ObtenerCalendarioPorIdQuery(calendario_id=calendario.id))

    # Assert
    assert resultado is calendario
    calendario_repo_mock.obtener_por_id.assert_awaited_once_with(calendario.id)
    calendario_repo_mock.guardar.assert_not_awaited()


async def test_obtener_calendario_por_id_inexistente_devuelve_none_sin_lanzar(
    calendario_repo_mock,
):
    # Arrange — el 404 lo decide el router, no el handler
    calendario_repo_mock.obtener_por_id.return_value = None
    handler = ObtenerCalendarioPorIdHandler(calendario_repo_mock)

    # Act
    resultado = await handler.ejecutar(ObtenerCalendarioPorIdQuery(calendario_id=uuid4()))

    # Assert
    assert resultado is None


async def test_obtener_calendario_de_un_paciente_consulta_por_paciente_id(
    calendario_repo_mock, construir_calendario
):
    # Arrange
    calendario = construir_calendario()
    calendario_repo_mock.obtener_por_paciente.return_value = calendario
    handler = ObtenerCalendarioPacienteHandler(calendario_repo_mock)

    # Act
    resultado = await handler.ejecutar(
        ObtenerCalendarioPacienteQuery(paciente_id=calendario.paciente_id)
    )

    # Assert
    assert resultado is calendario
    calendario_repo_mock.obtener_por_paciente.assert_awaited_once_with(calendario.paciente_id)
    calendario_repo_mock.obtener_por_id.assert_not_awaited()


async def test_listar_calendarios_activos_devuelve_la_lista_del_repositorio(
    calendario_repo_mock, construir_calendario
):
    # Arrange
    calendarios = [construir_calendario(), construir_calendario()]
    calendario_repo_mock.listar_activos.return_value = calendarios
    handler = ListarCalendariosActivosHandler(calendario_repo_mock)

    # Act
    resultado = await handler.ejecutar(ListarCalendariosActivosQuery())

    # Assert
    assert resultado == calendarios
    calendario_repo_mock.listar_activos.assert_awaited_once_with()


async def test_obtener_entregas_de_una_fecha_consulta_por_esa_fecha(
    calendario_repo_mock, construir_calendario
):
    # Arrange — HU-29: consolidado del día para planificar la producción
    fecha = date(2026, 1, 5)
    calendarios = [construir_calendario()]
    calendario_repo_mock.listar_con_entregas_en_fecha.return_value = calendarios
    handler = ObtenerEntregasDeFechaHandler(calendario_repo_mock)

    # Act
    resultado = await handler.ejecutar(ObtenerEntregasDeFechaQuery(fecha=fecha))

    # Assert
    assert resultado == calendarios
    calendario_repo_mock.listar_con_entregas_en_fecha.assert_awaited_once_with(fecha)


async def test_obtener_entregas_de_una_fecha_sin_entregas_devuelve_lista_vacia(
    calendario_repo_mock,
):
    # Arrange
    calendario_repo_mock.listar_con_entregas_en_fecha.return_value = []
    handler = ObtenerEntregasDeFechaHandler(calendario_repo_mock)

    # Act
    resultado = await handler.ejecutar(ObtenerEntregasDeFechaQuery(fecha=date(2026, 1, 5)))

    # Assert
    assert resultado == []


async def test_verificar_puede_modificar_con_anticipacion_suficiente_devuelve_cero_faltantes():
    # Arrange — servicio de dominio real: es Python puro, no hace falta doblarlo
    handler = VerificarPuedeModificarHandler(ValidadorCambioCalendarioService())

    # Act
    resultado = await handler.ejecutar(
        VerificarPuedeModificarQuery(fecha_entrega=date(2026, 1, 10), fecha_solicitud=date(2026, 1, 1))
    )

    # Assert
    assert resultado == {"puede_modificar": True, "dias_faltantes": 0}


async def test_verificar_puede_modificar_sin_anticipacion_informa_los_dias_que_faltan():
    # Arrange
    handler = VerificarPuedeModificarHandler(ValidadorCambioCalendarioService())

    # Act
    resultado = await handler.ejecutar(
        VerificarPuedeModificarQuery(fecha_entrega=date(2026, 1, 10), fecha_solicitud=date(2026, 1, 9))
    )

    # Assert
    assert resultado == {"puede_modificar": False, "dias_faltantes": 1}


async def test_verificar_puede_modificar_delega_ambas_preguntas_en_el_servicio():
    # Arrange — el servicio es síncrono: `Mock(spec=...)`, no `AsyncMock`
    servicio = Mock(spec=ValidadorCambioCalendarioService)
    servicio.puede_modificar.return_value = False
    servicio.dias_restantes_para_modificar.return_value = 7
    handler = VerificarPuedeModificarHandler(servicio)
    entrega, solicitud = date(2026, 1, 10), date(2026, 1, 9)

    # Act
    resultado = await handler.ejecutar(VerificarPuedeModificarQuery(entrega, solicitud))

    # Assert
    assert resultado == {"puede_modificar": False, "dias_faltantes": 7}
    servicio.puede_modificar.assert_called_once_with(entrega, solicitud)
    servicio.dias_restantes_para_modificar.assert_called_once_with(entrega, solicitud)
