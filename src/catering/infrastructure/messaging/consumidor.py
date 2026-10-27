"""Consumidor de eventos de integración de otros microservicios.

Una cola durable por microservicio, enlazada al exchange topic del grupo con las routing keys
que interesan. Cada mensaje se procesa en una transacción junto con su registro en
`eventos_procesados` (inbox): si el broker lo reentrega, se reconoce y no se aplica dos veces.
"""
import asyncio
import hashlib
import json
import logging
from collections.abc import Awaitable, Callable

import aio_pika
from aio_pika.abc import AbstractIncomingMessage, AbstractRobustConnection
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catering.infrastructure.persistence.orm_models import EventoProcesadoORM

logger = logging.getLogger(__name__)

Manejador = Callable[[AsyncSession, dict], Awaitable[None]]


class MensajeInvalidoError(ValueError):
    """El mensaje no cumple el contrato: no tiene sentido reintentarlo."""


class ConsumidorEventos:
    def __init__(
        self,
        session_factory: async_sessionmaker,
        rabbitmq_url: str,
        exchange: str,
        cola: str,
        manejadores: dict[str, Manejador],
    ) -> None:
        self._session_factory = session_factory
        self._rabbitmq_url = rabbitmq_url
        self._exchange_nombre = exchange
        self._cola_nombre = cola
        self._manejadores = manejadores
        self._conexion: AbstractRobustConnection | None = None
        self._tarea: asyncio.Task | None = None

    def iniciar(self) -> None:
        self._tarea = asyncio.create_task(self._conectar(), name="consumidor-eventos")

    async def detener(self) -> None:
        if self._tarea is not None:
            self._tarea.cancel()
            try:
                await self._tarea
            except asyncio.CancelledError:
                pass
        if self._conexion is not None:
            await self._conexion.close()

    async def _conectar(self) -> None:
        # El broker puede arrancar después que el servicio: se reintenta hasta conectar.
        # connect_robust reconecta solo y restaura cola y consumidor si la conexión se cae.
        while True:
            try:
                self._conexion = await aio_pika.connect_robust(self._rabbitmq_url, timeout=5)
                break
            except Exception as error:
                logger.warning("RabbitMQ no disponible (%s); reintento en 5 s", error)
                await asyncio.sleep(5)
        canal = await self._conexion.channel()
        await canal.set_qos(prefetch_count=10)
        exchange = await canal.declare_exchange(
            self._exchange_nombre, aio_pika.ExchangeType.TOPIC, durable=True
        )
        cola = await canal.declare_queue(self._cola_nombre, durable=True)
        for routing_key in self._manejadores:
            await cola.bind(exchange, routing_key=routing_key)
        await cola.consume(self._al_recibir)
        logger.info("Consumiendo %s ← %s", self._cola_nombre, ", ".join(self._manejadores))

    async def _al_recibir(self, mensaje: AbstractIncomingMessage) -> None:
        try:
            await self.procesar(mensaje.routing_key or "", mensaje.body, mensaje.message_id)
        except MensajeInvalidoError as error:
            logger.error("Mensaje descartado (%s): %s", mensaje.routing_key, error)
            await mensaje.reject(requeue=False)
            return
        except Exception:
            logger.exception("Fallo al procesar %s; se reintentará", mensaje.routing_key)
            await asyncio.sleep(1)
            await mensaje.nack(requeue=True)
            return
        await mensaje.ack()

    async def procesar(self, routing_key: str, cuerpo: bytes, message_id: str | None) -> bool:
        """Aplica el evento una sola vez. Devuelve False si ya se había procesado."""
        manejador = self._manejadores.get(routing_key)
        if manejador is None:
            raise MensajeInvalidoError(f"Sin manejador para {routing_key}")
        try:
            payload = json.loads(cuerpo)
        except ValueError as error:
            raise MensajeInvalidoError(f"JSON inválido: {error}") from error
        if not isinstance(payload, dict):
            raise MensajeInvalidoError("El payload debe ser un objeto JSON")
        # Sin message_id (otro productor no lo envía) se usa el hash del contenido.
        id_mensaje = message_id or hashlib.sha256(routing_key.encode() + cuerpo).hexdigest()

        try:
            async with self._session_factory() as session, session.begin():
                if await session.get(EventoProcesadoORM, id_mensaje) is not None:
                    logger.info("Evento %s ya procesado; se ignora", id_mensaje)
                    return False
                try:
                    await manejador(session, payload)
                except (KeyError, TypeError, ValueError) as error:
                    raise MensajeInvalidoError(f"Contrato incumplido: {error!r}") from error
                session.add(EventoProcesadoORM(message_id=id_mensaje, routing_key=routing_key))
        except IntegrityError:
            logger.info("Evento %s procesado en paralelo por otra réplica", id_mensaje)
            return False
        logger.info("Procesado %s (%s)", routing_key, id_mensaje)
        return True


def campo(payload: dict, *nombres: str):
    """Lee el primer nombre presente: los productores .NET publican camelCase y los Python snake_case."""
    for nombre in nombres:
        if nombre in payload:
            return payload[nombre]
    raise KeyError(nombres[0])
