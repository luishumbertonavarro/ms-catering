"""Registro del microservicio en Consul (Service Discovery).

Al arrancar, la instancia se anuncia con su IP y puerto, más un health check HTTP a /health.
El api-gateway pregunta a Consul por las instancias sanas y reparte las peticiones entre ellas.
"""
import asyncio
import logging
import socket

import httpx

logger = logging.getLogger(__name__)


class RegistroConsul:
    def __init__(
        self,
        consul_url: str,
        nombre: str,
        puerto: int,
        transport: httpx.AsyncBaseTransport | None = None,
        reintento_segundos: float = 5.0,
    ) -> None:
        self._consul_url = consul_url.rstrip("/")
        self._nombre = nombre
        self._puerto = puerto
        self._transport = transport
        self._reintento = reintento_segundos
        hostname = socket.gethostname()
        # IP del contenedor en la red de Docker: es la que el gateway y el health check pueden alcanzar.
        self._direccion = socket.gethostbyname(hostname)
        self.servicio_id = f"{nombre}-{hostname}"
        self._tarea: asyncio.Task | None = None

    def definicion(self) -> dict:
        return {
            "ID": self.servicio_id,
            "Name": self._nombre,
            "Address": self._direccion,
            "Port": self._puerto,
            "Tags": ["nurtricenter", "python", "fastapi"],
            "Check": {
                "HTTP": f"http://{self._direccion}:{self._puerto}/health",
                "Interval": "10s",
                "Timeout": "3s",
                "DeregisterCriticalServiceAfter": "1m",
            },
        }

    def _cliente(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=5, transport=self._transport)

    def iniciar(self) -> None:
        self._tarea = asyncio.create_task(self._registrar(), name="registro-consul")

    async def esperar_registro(self) -> None:
        if self._tarea is not None:
            await self._tarea

    async def _registrar(self) -> None:
        # Consul puede tardar en estar listo: reintentar sin bloquear el arranque de la API.
        while True:
            try:
                async with self._cliente() as client:
                    respuesta = await client.put(
                        f"{self._consul_url}/v1/agent/service/register", json=self.definicion()
                    )
                    respuesta.raise_for_status()
                logger.info(
                    "Registrado en Consul como %s (%s:%d)",
                    self.servicio_id, self._direccion, self._puerto,
                )
                return
            except httpx.HTTPError as error:
                logger.warning("Consul no disponible (%s); reintento en %.0f s", error, self._reintento)
                await asyncio.sleep(self._reintento)

    async def desregistrar(self) -> None:
        if self._tarea is not None and not self._tarea.done():
            self._tarea.cancel()
        try:
            async with self._cliente() as client:
                await client.put(
                    f"{self._consul_url}/v1/agent/service/deregister/{self.servicio_id}"
                )
            logger.info("Desregistrado de Consul: %s", self.servicio_id)
        except httpx.HTTPError as error:
            logger.warning("No se pudo desregistrar de Consul: %s", error)
