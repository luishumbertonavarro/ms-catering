"""Registro en Consul. Las llamadas HTTP se responden con httpx.MockTransport: no hay red ni Consul real."""
import httpx

from catering.infrastructure.discovery.consul import RegistroConsul


def _registro(manejador) -> tuple[RegistroConsul, list[httpx.Request]]:
    recibidas: list[httpx.Request] = []

    def _transport(request: httpx.Request) -> httpx.Response:
        recibidas.append(request)
        return manejador(request)

    registro = RegistroConsul(
        "http://consul:8500/", "ms-catering", 8000,
        transport=httpx.MockTransport(_transport), reintento_segundos=0,
    )
    return registro, recibidas


def test_definicion_anuncia_nombre_puerto_y_health_check_http():
    # Arrange
    registro, _ = _registro(lambda r: httpx.Response(200))

    # Act
    definicion = registro.definicion()

    # Assert
    assert definicion["Name"] == "ms-catering"
    assert definicion["ID"].startswith("ms-catering-")
    assert definicion["Port"] == 8000
    assert definicion["Check"]["HTTP"] == f"http://{definicion['Address']}:8000/health"
    assert definicion["Check"]["DeregisterCriticalServiceAfter"] == "1m"


async def test_registrar_hace_put_al_agente_de_consul_con_la_definicion():
    # Arrange
    registro, recibidas = _registro(lambda r: httpx.Response(200))

    # Act
    registro.iniciar()
    await registro.esperar_registro()

    # Assert
    assert len(recibidas) == 1
    assert recibidas[0].method == "PUT"
    assert recibidas[0].url == "http://consul:8500/v1/agent/service/register"


async def test_registrar_reintenta_mientras_consul_no_esta_disponible():
    # Arrange
    respuestas = iter([httpx.Response(500), httpx.Response(500), httpx.Response(200)])
    registro, recibidas = _registro(lambda r: next(respuestas))

    # Act
    registro.iniciar()
    await registro.esperar_registro()

    # Assert
    assert len(recibidas) == 3


async def test_desregistrar_borra_la_instancia_por_su_id():
    # Arrange
    registro, recibidas = _registro(lambda r: httpx.Response(200))

    # Act
    await registro.desregistrar()

    # Assert
    assert recibidas[0].url == (
        f"http://consul:8500/v1/agent/service/deregister/{registro.servicio_id}"
    )


async def test_desregistrar_con_consul_caido_no_lanza_excepcion():
    # Arrange
    def _caido(request):
        raise httpx.ConnectError("sin conexión")

    registro, _ = _registro(_caido)

    # Act / Assert — apagar el servicio no debe fallar por Consul
    await registro.desregistrar()
