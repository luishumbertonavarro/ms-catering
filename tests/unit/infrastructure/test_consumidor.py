"""Lógica pura del consumidor: validación del mensaje y lectura de campos camelCase/snake_case.

Las ramas que abren transacción (inbox, manejadores) se ejercitan contra RabbitMQ y PostgreSQL reales.
"""
import pytest

from catering.infrastructure.messaging import consumidor as modulo_consumidor

from catering.infrastructure.messaging.consumidor import (
    ConsumidorEventos,
    MensajeInvalidoError,
    campo,
)


def _consumidor() -> ConsumidorEventos:
    async def _manejador(session, payload):
        raise AssertionError("no debería llegar al manejador")

    return ConsumidorEventos(
        None, "amqp://x", "nurtricenter.events", "cola", {"contrato.cancelado": _manejador}
    )


def test_campo_lee_el_nombre_camel_case_de_productores_dotnet():
    # Act / Assert
    assert campo({"contratoId": "c1"}, "contratoId", "contrato_id") == "c1"


def test_campo_lee_el_nombre_snake_case_si_no_hay_camel_case():
    # Act / Assert
    assert campo({"contrato_id": "c1"}, "contratoId", "contrato_id") == "c1"


def test_campo_ausente_lanza_key_error():
    # Act / Assert
    with pytest.raises(KeyError):
        campo({}, "contratoId", "contrato_id")


async def test_procesar_routing_key_sin_manejador_es_mensaje_invalido():
    # Act / Assert
    with pytest.raises(MensajeInvalidoError):
        await _consumidor().procesar("otra.cosa", b"{}", "m1")


async def test_procesar_json_invalido_es_mensaje_invalido():
    # Act / Assert
    with pytest.raises(MensajeInvalidoError):
        await _consumidor().procesar("contrato.cancelado", b"no-es-json", "m1")


async def test_procesar_payload_que_no_es_objeto_es_mensaje_invalido():
    # Act / Assert
    with pytest.raises(MensajeInvalidoError):
        await _consumidor().procesar("contrato.cancelado", b"[1, 2]", "m1")


class _MensajeFalso:
    """Lo mínimo de AbstractIncomingMessage que usa el consumidor: registra cómo se confirmó."""

    routing_key = "contrato.cancelado"
    body = b"{}"
    message_id = "m1"

    def __init__(self) -> None:
        self.resultado: str | None = None

    async def ack(self) -> None:
        self.resultado = "ack"

    async def reject(self, requeue: bool) -> None:
        self.resultado = f"reject(requeue={requeue})"

    async def nack(self, requeue: bool) -> None:
        self.resultado = f"nack(requeue={requeue})"


async def _recibir(monkeypatch, efecto) -> str:
    consumidor = _consumidor()

    async def _procesar(routing_key, cuerpo, message_id):
        if efecto is not None:
            raise efecto
        return True

    async def _sin_espera(segundos):
        return None

    monkeypatch.setattr(consumidor, "procesar", _procesar)
    monkeypatch.setattr(modulo_consumidor.asyncio, "sleep", _sin_espera)
    mensaje = _MensajeFalso()
    await consumidor._al_recibir(mensaje)
    return mensaje.resultado


async def test_mensaje_procesado_se_confirma_con_ack(monkeypatch):
    # Act / Assert
    assert await _recibir(monkeypatch, None) == "ack"


async def test_mensaje_invalido_se_rechaza_sin_reencolar(monkeypatch):
    # Act / Assert — reintentarlo no lo arreglaría
    assert await _recibir(monkeypatch, MensajeInvalidoError("x")) == "reject(requeue=False)"


async def test_fallo_transitorio_se_devuelve_a_la_cola_para_reintentar(monkeypatch):
    # Act / Assert — p. ej. la BD estaba caída
    assert await _recibir(monkeypatch, RuntimeError("BD caída")) == "nack(requeue=True)"
