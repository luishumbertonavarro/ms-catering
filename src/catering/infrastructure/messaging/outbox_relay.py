"""Relay del Transactional Outbox: lee los eventos pendientes de la tabla `outbox` y los publica en RabbitMQ.

El caso de uso nunca habla con el broker: solo guarda el agregado y su fila de outbox en una misma
transacción. Este proceso, aparte, publica lo pendiente. Si RabbitMQ está caído la fila queda
pendiente (sube `intentos`) y se reintenta en la siguiente vuelta: ningún evento se pierde.
"""
import asyncio
import json
import logging
from datetime import datetime, timezone

import aio_pika
from aio_pika.abc import AbstractChannel, AbstractConnection, AbstractExchange
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from catering.infrastructure.persistence.orm_models import OutboxORM

logger = logging.getLogger(__name__)

_LOTE = 50
_TIMEOUT_PUBLICACION_SEGUNDOS = 5.0


class OutboxRelay:
    def __init__(
        self,
        session_factory: async_sessionmaker,
        rabbitmq_url: str,
        exchange: str,
        intervalo_segundos: float = 2.0,
    ) -> None:
        self._session_factory = session_factory
        self._rabbitmq_url = rabbitmq_url
        self._exchange_nombre = exchange
        self._intervalo = intervalo_segundos
        self._conexion: AbstractConnection | None = None
        self._canal: AbstractChannel | None = None
        self._exchange: AbstractExchange | None = None
        self._tarea: asyncio.Task | None = None

    def iniciar(self) -> None:
        self._tarea = asyncio.create_task(self._bucle(), name="outbox-relay")

    async def detener(self) -> None:
        if self._tarea is not None:
            self._tarea.cancel()
            try:
                await self._tarea
            except asyncio.CancelledError:
                pass
        await self._cerrar_conexion()

    async def _bucle(self) -> None:
        logger.info("Outbox relay iniciado (exchange=%s)", self._exchange_nombre)
        while True:
            try:
                await self.publicar_pendientes()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Error inesperado en el outbox relay")
            await asyncio.sleep(self._intervalo)

    async def publicar_pendientes(self) -> int:
        """Publica un lote de pendientes. Devuelve cuántos se publicaron."""
        publicados = 0
        async with self._session_factory() as session, session.begin():
            # SKIP LOCKED: con varias réplicas, cada fila la toma un solo relay.
            filas = (
                await session.execute(
                    select(OutboxORM)
                    .where(OutboxORM.publicado_en.is_(None))
                    .order_by(OutboxORM.ocurrido_en)
                    .limit(_LOTE)
                    .with_for_update(skip_locked=True)
                )
            ).scalars().all()
            for fila in filas:
                try:
                    exchange = await self._obtener_exchange()
                    await asyncio.wait_for(
                        exchange.publish(_a_mensaje_amqp(fila), routing_key=fila.routing_key),
                        timeout=_TIMEOUT_PUBLICACION_SEGUNDOS,
                    )
                except Exception as error:
                    fila.intentos += 1
                    fila.ultimo_error = f"{type(error).__name__}: {error}"[:500]
                    logger.warning(
                        "No se pudo publicar %s (%s), intento %d: %s",
                        fila.tipo, fila.id, fila.intentos, fila.ultimo_error,
                    )
                    await self._cerrar_conexion()
                    break  # se conserva el orden: el resto espera a la próxima vuelta
                fila.publicado_en = datetime.now(timezone.utc)
                publicados += 1
                logger.info("Publicado %s → %s (%s)", fila.tipo, fila.routing_key, fila.id)
        return publicados

    async def _obtener_exchange(self) -> AbstractExchange:
        if self._exchange is None:
            self._conexion = await aio_pika.connect(self._rabbitmq_url, timeout=5)
            # publisher_confirms (por defecto en aio-pika): publish() espera el ack del broker.
            self._canal = await self._conexion.channel()
            self._exchange = await self._canal.declare_exchange(
                self._exchange_nombre, aio_pika.ExchangeType.TOPIC, durable=True
            )
        return self._exchange

    async def _cerrar_conexion(self) -> None:
        conexion, self._conexion, self._canal, self._exchange = self._conexion, None, None, None
        if conexion is not None and not conexion.is_closed:
            try:
                await conexion.close()
            except Exception:
                pass


def _a_mensaje_amqp(fila: OutboxORM) -> aio_pika.Message:
    return aio_pika.Message(
        body=json.dumps(fila.payload, ensure_ascii=False).encode("utf-8"),
        content_type="application/json",
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        message_id=str(fila.id),  # el consumidor lo usa para la idempotencia
        type=fila.tipo,
        timestamp=fila.ocurrido_en,
    )
