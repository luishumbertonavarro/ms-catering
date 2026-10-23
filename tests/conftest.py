"""Fixtures compartidas por la suite de pruebas UNITARIAS.

Se divide en dos bloques:

1. **Builders de dominio** — construyen objetos reales del modelo para no repetir
   el mismo armado en cada test.
2. **Mocks de los puertos** — dobles de prueba que sustituyen al repositorio.

Las pruebas de integración (`tests/integration/`) **no** usan nada de aquí: tienen
su propio `conftest.py` y trabajan sin dobles, contra PostgreSQL real.
"""

from datetime import date
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from catering.domain.model import (
    CalendarioEntrega,
    DireccionEntrega,
    EstadoCalendario,
)
from catering.domain.repositories import CalendarioEntregaRepository

# Fechas fijas: los tests nunca deben depender de "hoy", o dejarían de ser
# deterministas y fallarían en función del día en que se ejecuten.
FECHA_INICIO = date(2026, 1, 1)
FECHA_FIN = date(2026, 1, 15)

# Fecha de solicitud con anticipación de sobra para cualquier día del calendario
# por defecto (la regla exige >= 2 días; aquí hay 12 o más).
FECHA_SOLICITUD_VALIDA = date(2025, 12, 20)


# ---------------------------------------------------------------------------
# Builders de dominio
# ---------------------------------------------------------------------------

@pytest.fixture
def direccion_domicilio() -> DireccionEntrega:
    """Dirección de entrega válida de referencia (la inicial del calendario)."""
    return DireccionEntrega(
        direccion="Av. Banzer 123",
        referencia="Portón verde",
        zona="Equipetrol",
    )


@pytest.fixture
def direccion_trabajo() -> DireccionEntrega:
    """Segunda dirección válida, distinta de la inicial."""
    return DireccionEntrega(
        direccion="Calle Libertad 456, piso 3",
        referencia="Oficina 3B",
        zona="Centro",
    )


@pytest.fixture
def construir_calendario(direccion_domicilio):
    """Factory de CalendarioEntrega.

    Por defecto devuelve un calendario ACTIVO del 2026-01-01 al 2026-01-15
    (15 entregas PROGRAMADAS en la dirección de domicilio). Los parámetros
    permiten variar solo lo que el test necesita:

        cal = construir_calendario()                                   # 15 días, activo
        cal = construir_calendario(fecha_fin=date(2026, 1, 1))         # un solo día
        cal = construir_calendario(estado=EstadoCalendario.CANCELADO)  # no modificable
        cal = construir_calendario(plan_nutricional_id=uuid4())
    """

    def _construir(
        fecha_inicio: date = FECHA_INICIO,
        fecha_fin: date = FECHA_FIN,
        estado: EstadoCalendario = EstadoCalendario.ACTIVO,
        plan_nutricional_id=None,
    ) -> CalendarioEntrega:
        calendario = CalendarioEntrega.crear(
            paciente_id=uuid4(),
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            direccion_default=direccion_domicilio,
            plan_nutricional_id=plan_nutricional_id,
        )
        # El estado se cambia al final: un calendario no ACTIVO ya no admite cambios.
        if estado is EstadoCalendario.CANCELADO:
            calendario.cancelar_calendario()
        elif estado is EstadoCalendario.COMPLETADO:
            calendario.completar_calendario()
        elif estado is EstadoCalendario.PAUSADO:
            # PAUSADO no tiene método de dominio que lleve a él: solo puede llegar
            # rehidratado desde el repositorio, por el constructor (que no valida).
            calendario = CalendarioEntrega(
                id=calendario.id,
                paciente_id=calendario.paciente_id,
                fecha_inicio=calendario.fecha_inicio,
                fecha_fin=calendario.fecha_fin,
                estado=EstadoCalendario.PAUSADO,
                entregas=calendario.entregas,
                direcciones_habituales=[],
                dias_sin_entrega=[],
                plan_nutricional_id=calendario.plan_nutricional_id,
            )
        return calendario

    return _construir


# ---------------------------------------------------------------------------
# Mocks de los puertos (interfaces ABC definidas en el dominio)
# ---------------------------------------------------------------------------

@pytest.fixture
def calendario_repo_mock() -> AsyncMock:
    """Doble de CalendarioEntregaRepository (guardar / obtener_por_id / ...)."""
    return AsyncMock(spec=CalendarioEntregaRepository)
