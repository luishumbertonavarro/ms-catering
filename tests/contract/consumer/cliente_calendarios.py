"""Cliente HTTP de `app-paciente`, el consumer simulado de ms-catering.

Representa la app móvil del paciente (HU-25: "consultar mi calendario de
entregas desde la app"). En un sistema real viviría en el repositorio de la app;
aquí se incluye para que el contrato se genere a partir de **código cliente
real**, no de una petición escrita a mano en el test.
"""
from uuid import UUID

import httpx


class CalendarioNoEncontrado(Exception):
    """ms-catering respondió 404 para el calendario pedido."""


class ClienteCalendarios:
    def __init__(self, base_url: str) -> None:
        self._base_url = str(base_url).rstrip("/")

    async def obtener_calendario(self, calendario_id: UUID) -> dict:
        async with httpx.AsyncClient(base_url=self._base_url) as client:
            respuesta = await client.get(
                f"/calendarios/{calendario_id}", headers={"Accept": "application/json"}
            )
        if respuesta.status_code == 404:
            raise CalendarioNoEncontrado(str(calendario_id))
        respuesta.raise_for_status()
        return respuesta.json()

    async def obtener_calendario_paciente(self, paciente_id: UUID) -> dict:
        async with httpx.AsyncClient(base_url=self._base_url) as client:
            respuesta = await client.get(
                f"/calendarios/paciente/{paciente_id}", headers={"Accept": "application/json"}
            )
        if respuesta.status_code == 404:
            raise CalendarioNoEncontrado(str(paciente_id))
        respuesta.raise_for_status()
        return respuesta.json()
