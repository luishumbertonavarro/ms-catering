"""Pruebas de integración del agregado CalendarioEntrega — flujo correcto.

Lo que aquí se verifica no lo puede ver una prueba unitaria: que el estado
**sobrevive de una petición HTTP a la siguiente** porque de verdad se escribió en
PostgreSQL, y que el mapeo dominio ↔ ORM reconstruye la jerarquía completa
calendario → entregas → direcciones habituales.

Por eso el test principal es uno solo y largo: partirlo en pedazos rompería
justamente lo que se quiere demostrar, que es la continuidad del estado.

**Sobre las fechas.** Los endpoints de modificación usan `date.today()` como
fecha de solicitud (el cliente no la envía). Para que la regla de los 2 días no
haga a los tests depender del día en que se ejecutan, los calendarios de este
archivo están en **2099**: siempre faltan más de 2 días. El camino de
"anticipación insuficiente" usa el extremo opuesto, un calendario en **2020**.
"""

from uuid import uuid4

import pytest

pytestmark = pytest.mark.integration

# Fechas fijas y lejanas (ver docstring del módulo).
FECHA_INICIO = "2099-01-01"
FECHA_FIN = "2099-01-15"

DIRECCION_INICIAL = {
    "direccion": "Av. Banzer 123",
    "referencia": "Portón verde",
    "zona": "Equipetrol",
}
DIRECCION_TRABAJO = {
    "direccion": "Calle Libertad 456, piso 3",
    "referencia": "Oficina 3B",
    "zona": "Centro",
}


def cuerpo_calendario(
    paciente_id: str,
    fecha_inicio: str = FECHA_INICIO,
    fecha_fin: str = FECHA_FIN,
    plan_nutricional_id: str | None = None,
) -> dict:
    """Cuerpo válido de `POST /calendarios`."""
    return {
        "paciente_id": paciente_id,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "direccion_inicial": DIRECCION_INICIAL,
        "plan_nutricional_id": plan_nutricional_id,
    }


def entrega_del(calendario: dict, fecha: str) -> dict:
    """La entrega de una fecha concreta dentro de un `CalendarioResponse`."""
    return next(e for e in calendario["entregas"] if e["fecha"] == fecha)


async def test_ciclo_de_vida_completo_de_un_calendario_persiste_en_la_base(cliente):
    """Recorre el calendario de punta a punta: crearlo, personalizarlo y cancelarlo.

    Cada paso es una petición HTTP independiente. Que el paso N vea lo que hizo
    el paso N-1 solo es posible si el repositorio escribió realmente en la base.
    """
    # Arrange
    paciente_id = str(uuid4())
    plan_id = str(uuid4())

    # Act / Assert — 1. Crear el calendario (HU-25)
    respuesta = await cliente.post(
        "/calendarios", json=cuerpo_calendario(paciente_id, plan_nutricional_id=plan_id)
    )

    assert respuesta.status_code == 201
    calendario = respuesta.json()
    calendario_id = calendario["id"]
    assert calendario["paciente_id"] == paciente_id
    assert calendario["plan_nutricional_id"] == plan_id
    assert calendario["estado"] == "ACTIVO"
    assert calendario["total_dias"] == 15
    assert len(calendario["entregas"]) == 15
    assert {e["estado"] for e in calendario["entregas"]} == {"PROGRAMADA"}
    assert calendario["direcciones_habituales"] == []

    # Act / Assert — 2. Releerlo: las 15 entregas vuelven de la base
    respuesta = await cliente.get(f"/calendarios/{calendario_id}")

    assert respuesta.status_code == 200
    calendario = respuesta.json()
    assert len(calendario["entregas"]) == 15
    primera = entrega_del(calendario, FECHA_INICIO)
    assert primera["direccion"] == "Av. Banzer 123"
    assert primera["referencia"] == "Portón verde"
    assert primera["zona"] == "Equipetrol"
    assert primera["tiene_etiqueta"] is False

    # Act / Assert — 3. Cambiar la dirección de un día (HU-26)
    respuesta = await cliente.patch(
        f"/calendarios/{calendario_id}/entregas/2099-01-03/direccion",
        json={"nueva_direccion": DIRECCION_TRABAJO},
    )
    assert respuesta.status_code == 204

    entregas = (await cliente.get(f"/calendarios/{calendario_id}/entregas")).json()
    cambiada = next(e for e in entregas if e["fecha"] == "2099-01-03")
    assert cambiada["direccion"] == "Calle Libertad 456, piso 3"
    assert cambiada["zona"] == "Centro"
    # Solo ese día: el siguiente conserva la dirección inicial.
    assert next(e for e in entregas if e["fecha"] == "2099-01-04")["direccion"] == "Av. Banzer 123"

    # Act / Assert — 4. Registrar una dirección habitual (HU-30)
    respuesta = await cliente.post(
        f"/calendarios/{calendario_id}/direcciones",
        json={"nombre": "trabajo", "direccion": DIRECCION_TRABAJO, "es_principal": True},
    )
    assert respuesta.status_code == 204

    direcciones = (await cliente.get(f"/calendarios/{calendario_id}/direcciones")).json()
    assert len(direcciones) == 1
    assert direcciones[0]["nombre"] == "trabajo"
    assert direcciones[0]["es_principal"] is True

    # Act / Assert — 5. Asignar esa dirección habitual a otro día (HU-30)
    respuesta = await cliente.patch(
        f"/calendarios/{calendario_id}/entregas/2099-01-06/direccion-habitual",
        json={"nombre_direccion": "trabajo"},
    )
    assert respuesta.status_code == 204

    calendario = (await cliente.get(f"/calendarios/{calendario_id}")).json()
    assert entrega_del(calendario, "2099-01-06")["direccion"] == "Calle Libertad 456, piso 3"

    # Act / Assert — 6. Marcar un día sin entrega (HU-27)
    respuesta = await cliente.patch(
        f"/calendarios/{calendario_id}/entregas/2099-01-10/sin-entrega",
        json={"motivo": "Viaje de trabajo"},
    )
    assert respuesta.status_code == 204

    calendario = (await cliente.get(f"/calendarios/{calendario_id}")).json()
    assert entrega_del(calendario, "2099-01-10")["estado"] == "SIN_ENTREGA"

    # Act / Assert — 7. Consultarlo por paciente, como lo hace la app (HU-25)
    respuesta = await cliente.get(f"/calendarios/paciente/{paciente_id}")
    assert respuesta.status_code == 200
    assert respuesta.json()["id"] == calendario_id

    # Act / Assert — 8. Cancelar el calendario
    respuesta = await cliente.delete(f"/calendarios/{calendario_id}")
    assert respuesta.status_code == 204

    calendario = (await cliente.get(f"/calendarios/{calendario_id}")).json()
    assert calendario["estado"] == "CANCELADO"
    # La cascada solo cancela las PROGRAMADAS; el día sin entrega lo sigue siendo.
    assert entrega_del(calendario, "2099-01-10")["estado"] == "SIN_ENTREGA"
    otras = {e["estado"] for e in calendario["entregas"] if e["fecha"] != "2099-01-10"}
    assert otras == {"CANCELADA"}
    # Y la dirección habitual sigue registrada.
    assert len(calendario["direcciones_habituales"]) == 1


async def test_crear_calendario_de_un_solo_dia_genera_una_unica_entrega(cliente):
    # Arrange
    cuerpo = cuerpo_calendario(str(uuid4()), fecha_inicio="2099-03-01", fecha_fin="2099-03-01")

    # Act
    respuesta = await cliente.post("/calendarios", json=cuerpo)

    # Assert
    assert respuesta.status_code == 201
    assert respuesta.json()["total_dias"] == 1
    assert respuesta.json()["entregas"][0]["fecha"] == "2099-03-01"


async def test_crear_calendario_sin_plan_nutricional_lo_guarda_con_plan_nulo(cliente):
    # Arrange
    cuerpo = cuerpo_calendario(str(uuid4()))
    del cuerpo["plan_nutricional_id"]

    # Act
    calendario_id = (await cliente.post("/calendarios", json=cuerpo)).json()["id"]

    # Assert
    calendario = (await cliente.get(f"/calendarios/{calendario_id}")).json()
    assert calendario["plan_nutricional_id"] is None


async def test_listar_calendarios_activos_devuelve_solo_los_activos(cliente):
    # Arrange
    activo_id = (await cliente.post("/calendarios", json=cuerpo_calendario(str(uuid4())))).json()["id"]
    cancelado_id = (
        await cliente.post("/calendarios", json=cuerpo_calendario(str(uuid4())))
    ).json()["id"]
    await cliente.delete(f"/calendarios/{cancelado_id}")

    # Act
    respuesta = await cliente.get("/calendarios")

    # Assert — se comprueba pertenencia, no igualdad: el listado podría contener
    # calendarios preexistentes en la base de desarrollo y el test no debe asumir
    # que está vacía.
    assert respuesta.status_code == 200
    ids = [c["id"] for c in respuesta.json()]
    assert activo_id in ids
    assert cancelado_id not in ids


async def test_entregas_de_una_fecha_incluye_solo_calendarios_con_entrega_programada(cliente):
    """HU-29: el consolidado del día que usa cocina para planificar la producción."""
    # Arrange
    cuerpo = {"fecha_inicio": "2099-02-01", "fecha_fin": "2099-02-15"}
    con_entrega_id = (
        await cliente.post("/calendarios", json=cuerpo_calendario(str(uuid4()), **cuerpo))
    ).json()["id"]
    sin_entrega_id = (
        await cliente.post("/calendarios", json=cuerpo_calendario(str(uuid4()), **cuerpo))
    ).json()["id"]
    await cliente.patch(f"/calendarios/{sin_entrega_id}/entregas/2099-02-10/sin-entrega", json={})
    cancelado_id = (
        await cliente.post("/calendarios", json=cuerpo_calendario(str(uuid4()), **cuerpo))
    ).json()["id"]
    await cliente.delete(f"/calendarios/{cancelado_id}")

    # Act
    respuesta = await cliente.get("/calendarios/entregas/fecha/2099-02-10")

    # Assert
    assert respuesta.status_code == 200
    ids = [c["id"] for c in respuesta.json()]
    assert con_entrega_id in ids
    assert sin_entrega_id not in ids
    assert cancelado_id not in ids


async def test_entregas_de_una_fecha_devuelve_el_calendario_completo_sin_duplicarlo(cliente):
    """El JOIN con `entregas` multiplicaría filas; `unique()` debe deduplicarlas."""
    # Arrange
    calendario_id = (
        await cliente.post("/calendarios", json=cuerpo_calendario(str(uuid4())))
    ).json()["id"]

    # Act
    calendarios = (await cliente.get("/calendarios/entregas/fecha/2099-01-05")).json()

    # Assert
    propios = [c for c in calendarios if c["id"] == calendario_id]
    assert len(propios) == 1
    assert len(propios[0]["entregas"]) == 15


async def test_verificar_modificacion_con_anticipacion_suficiente_permite_modificar(cliente):
    # Act
    respuesta = await cliente.get(
        "/calendarios/verificar-modificacion",
        params={"fecha_entrega": "2026-01-10", "fecha_solicitud": "2026-01-01"},
    )

    # Assert
    assert respuesta.status_code == 200
    assert respuesta.json() == {"puede_modificar": True, "dias_faltantes": 0}


async def test_verificar_modificacion_con_un_dia_de_anticipacion_informa_lo_que_falta(cliente):
    # Act
    respuesta = await cliente.get(
        "/calendarios/verificar-modificacion",
        params={"fecha_entrega": "2026-01-10", "fecha_solicitud": "2026-01-09"},
    )

    # Assert
    assert respuesta.status_code == 200
    assert respuesta.json() == {"puede_modificar": False, "dias_faltantes": 1}


async def test_obtener_calendario_de_un_paciente_ignora_sus_calendarios_cancelados(cliente):
    # Arrange
    paciente_id = str(uuid4())
    viejo_id = (await cliente.post("/calendarios", json=cuerpo_calendario(paciente_id))).json()["id"]
    await cliente.delete(f"/calendarios/{viejo_id}")
    nuevo_id = (
        await cliente.post(
            "/calendarios",
            json=cuerpo_calendario(paciente_id, fecha_inicio="2099-02-01", fecha_fin="2099-02-15"),
        )
    ).json()["id"]

    # Act
    respuesta = await cliente.get(f"/calendarios/paciente/{paciente_id}")

    # Assert
    assert respuesta.status_code == 200
    assert respuesta.json()["id"] == nuevo_id


# ---------------------------------------------------------------------------
# Aislamiento: los dos tests siguientes van en pareja
# ---------------------------------------------------------------------------

# Un paciente fijo compartido por los dos tests de abajo. El primero le crea un
# calendario; el segundo comprueba que ya no existe.
PACIENTE_DE_PRUEBA_DE_AISLAMIENTO = "11111111-1111-1111-1111-111111111111"


async def test_aislamiento_paso_1_crea_un_calendario_para_un_paciente_fijo(cliente):
    """Primera mitad de la demostración del aislamiento transaccional."""
    # Act
    respuesta = await cliente.post(
        "/calendarios", json=cuerpo_calendario(PACIENTE_DE_PRUEBA_DE_AISLAMIENTO)
    )

    # Assert — dentro de este test el calendario existe y se puede consultar
    assert respuesta.status_code == 201
    consulta = await cliente.get(f"/calendarios/paciente/{PACIENTE_DE_PRUEBA_DE_AISLAMIENTO}")
    assert consulta.status_code == 200


async def test_aislamiento_paso_2_el_calendario_del_test_anterior_ya_no_existe(cliente):
    """Segunda mitad: el calendario creado arriba desapareció al revertir la transacción.

    Es la prueba de que las pruebas de integración **no ensucian la base de
    datos**: cada test corre dentro de una transacción que se revierte al
    terminar (ver la fixture `cliente` en `conftest.py`).

    Ejecutado por separado este test también pasa, así que no introduce una
    dependencia real de orden.
    """
    # Act
    respuesta = await cliente.get(f"/calendarios/paciente/{PACIENTE_DE_PRUEBA_DE_AISLAMIENTO}")

    # Assert
    assert respuesta.status_code == 404
