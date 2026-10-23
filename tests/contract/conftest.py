"""Fixtures compartidas de las pruebas de contrato (Pact).

Glosario rápido:

- **Consumer**: quien hace la petición y *escribe* el contrato.
- **Provider**: quien responde y *verifica* el contrato.
- **Pact file**: el JSON en `pacts/` con las interacciones esperadas.
- **Provider state**: la precondición (`given(...)`) que el provider prepara antes
  de reproducir cada interacción.

Relaciones de este repositorio:

    app-paciente ──(consume)──▶  ms-catering    (verificado aquí)
    ms-catering  ──(consume)──▶  ms-pacientes   (lo verifica el otro equipo)
"""

import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from pact import Pact
from pact.pact import PactServer

RAIZ = Path(__file__).resolve().parents[2]
CARPETA_PACTS = RAIZ / "pacts"


@pytest.fixture(scope="session")
def carpeta_pacts() -> Path:
    """Carpeta donde el consumer escribe y el provider lee los contratos."""
    CARPETA_PACTS.mkdir(exist_ok=True)
    return CARPETA_PACTS


def contrato_limpio(carpeta: Path, consumer: str, provider: str) -> Path:
    """Borra el pact de una relación para regenerarlo desde cero.

    Cada test consumer escribe su interacción con `overwrite=False` (se fusiona
    con el archivo). Borrarlo al inicio del módulo evita que sobrevivan
    interacciones de un test que ya se eliminó.
    """
    archivo = carpeta / f"{consumer}-{provider}.json"
    archivo.unlink(missing_ok=True)
    return archivo


@contextmanager
def mock_server(pact: Pact, espera_maxima: float = 3.0) -> Iterator[PactServer]:
    """`pact.serve()` que espera a que el mock registre las peticiones recibidas.

    En Windows, el núcleo Rust de Pact puede responder a la primera petición
    unos milisegundos antes de marcarla como recibida. Sin esta espera, el
    `__exit__` de `serve()` informa de un falso "Missing request". Si al vencer el
    plazo sigue sin coincidir, `serve()` lanza el error real con sus diferencias.
    """
    with pact.serve() as servidor:
        yield servidor
        limite = time.monotonic() + espera_maxima
        while not servidor.matched and time.monotonic() < limite:
            time.sleep(0.02)
