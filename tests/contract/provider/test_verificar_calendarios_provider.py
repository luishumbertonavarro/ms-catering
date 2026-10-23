"""Verificación del provider: ms-catering cumple el contrato de `app-paciente`.

Pact lee `pacts/app-paciente-ms-catering.json` y, para cada interacción:

1. llama a `POST /_pact/provider-states` (`setup`) para preparar el estado;
2. reproduce la petición contra la API real, levantada con uvicorn;
3. compara la respuesta con los matchers del contrato;
4. llama otra vez a la ruta de estados (`teardown`) para deshacer los datos.

La app corre sobre PostgreSQL real, dentro de una transacción que se revierte al
apagar el servidor (ver `app_provider.py`).
"""
import asyncio
import os
import socket
import threading
import time
from collections.abc import Iterator

import httpx
import pytest
import uvicorn
from pact import Verifier

from catering.infrastructure.config.settings import settings
from tests.contract.provider.app_provider import RUTA_ESTADOS, crear_app_provider
from tests.integration.conftest import _hay_conexion

pytestmark = pytest.mark.contract

PROVIDER = "ms-catering"
CONTRATOS_VERIFICADOS = ["app-paciente-ms-catering.json"]


def _puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def url_bd_provider() -> str:
    url = os.getenv("TEST_DATABASE_URL") or settings.database_url
    try:
        asyncio.run(_hay_conexion(url))
    except Exception as exc:  # noqa: BLE001 — cualquier fallo aquí es "no disponible"
        pytest.skip(
            "PostgreSQL no está disponible o no tiene el esquema; se omite la verificación "
            "del provider. Levántalo con: docker compose up -d catering_db && "
            f"uv run alembic upgrade head ({type(exc).__name__}: {exc})"
        )
    return url


@pytest.fixture(scope="module")
def servidor_provider(url_bd_provider: str) -> Iterator[str]:
    """Levanta la app de verificación con uvicorn en un hilo y devuelve su URL."""
    puerto = _puerto_libre()
    config = uvicorn.Config(
        crear_app_provider(url_bd_provider),
        host="127.0.0.1",
        port=puerto,
        log_level="warning",
        lifespan="on",
    )
    servidor = uvicorn.Server(config)
    hilo = threading.Thread(target=servidor.run, daemon=True)
    hilo.start()

    limite = time.monotonic() + 15
    while not servidor.started:
        if time.monotonic() > limite or not hilo.is_alive():
            pytest.fail("No se pudo levantar la app del provider con uvicorn.")
        time.sleep(0.05)

    try:
        yield f"http://127.0.0.1:{puerto}"
    finally:
        servidor.should_exit = True
        hilo.join(timeout=15)


@pytest.mark.parametrize("contrato", CONTRATOS_VERIFICADOS)
def test_provider_cumple_el_contrato_de_sus_consumers(servidor_provider, carpeta_pacts, contrato):
    # Arrange
    archivo = carpeta_pacts / contrato
    if not archivo.exists():
        pytest.skip(f"No existe {archivo.name}. Genéralo con: uv run pytest tests/contract/consumer")
    assert httpx.get(f"{servidor_provider}/calendarios").status_code == 200

    verificador = (
        Verifier(PROVIDER, host="127.0.0.1")
        .add_transport(url=servidor_provider)
        .add_source(archivo)
        .state_handler(f"{servidor_provider}{RUTA_ESTADOS}", teardown=True, body=True)
    )

    # Act / Assert — `verify()` lanza una excepción con el detalle si algo no cumple
    verificador.verify()
