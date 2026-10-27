"""El lifespan arranca relay, consumidor y registro en Consul solo si están configurados.

Se ejecuta el context manager directamente. Los procesos se sustituyen por registros en memoria:
no se toca broker, Consul ni base de datos.
"""
import pytest

from catering.infrastructure.config import settings
from catering.infrastructure.discovery.consul import RegistroConsul
from catering.infrastructure.messaging.consumidor import ConsumidorEventos
from catering.infrastructure.messaging.outbox_relay import OutboxRelay
from catering.presentation.api.main import app, lifespan


@pytest.fixture
def llamadas(monkeypatch) -> list[str]:
    registro: list[str] = []
    for clase, inicio, fin in [
        (OutboxRelay, "iniciar", "detener"),
        (ConsumidorEventos, "iniciar", "detener"),
        (RegistroConsul, "iniciar", "desregistrar"),
    ]:
        nombre = clase.__name__

        def _iniciar(self, nombre=nombre):
            registro.append(f"{nombre}.iniciar")

        async def _detener(self, nombre=nombre):
            registro.append(f"{nombre}.detener")

        monkeypatch.setattr(clase, inicio, _iniciar)
        monkeypatch.setattr(clase, fin, _detener)
    return registro


async def test_lifespan_sin_broker_ni_consul_no_arranca_procesos(monkeypatch, llamadas):
    # Arrange
    monkeypatch.setattr(settings, "rabbitmq_url", "")
    monkeypatch.setattr(settings, "consul_url", "")

    # Act
    async with lifespan(app):
        pass

    # Assert
    assert llamadas == []


async def test_lifespan_con_broker_y_consul_arranca_y_detiene_los_procesos(monkeypatch, llamadas):
    # Arrange
    monkeypatch.setattr(settings, "rabbitmq_url", "amqp://guest:guest@rabbitmq/")
    monkeypatch.setattr(settings, "consul_url", "http://consul:8500")

    # Act
    async with lifespan(app):
        arrancados = list(llamadas)

    # Assert
    assert arrancados == [
        "RegistroConsul.iniciar",
        "OutboxRelay.iniciar",
        "ConsumidorEventos.iniciar",
    ]
    assert llamadas[3:] == [
        "OutboxRelay.detener",
        "ConsumidorEventos.detener",
        "RegistroConsul.detener",
    ]
