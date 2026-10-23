---
name: integration-testing-catering
description: Convenciones de pruebas de integración de ms-catering — cliente httpx sobre la app FastAPI real, aislamiento por transacción reversible sobre PostgreSQL, fechas 2099/2020 por la regla de 2 días, mapeo de errores de dominio a HTTP y sincronización con la colección Postman. Úsala al escribir, revisar o depurar cualquier test de tests/integration/ o la colección de postman/.
---

# Convenciones de pruebas de integración — ms-catering

Complemento de `testing-catering` (unitarias). Aquí solo `tests/integration/` y `postman/`.

## 1. Qué es

```
HTTP → router → caso de uso → repositorio SQLAlchemy → PostgreSQL → HTTP
```

Sin dobles. Prueba lo que un mock oculta: la carga y escritura completa del
agregado (mapeo ORM), la traducción de errores a `(status, tipo)` y el
`commit`/`rollback`. Nunca repitas una regla de negocio ya cubierta en unitarias.

## 2. El aislamiento

Se usa `db_catering`, la de desarrollo, **sin ensuciarla**:

```python
conexion = await motor_test.connect()
transaccion = await conexion.begin()                  # 1. transacción externa
fabrica_sesion = async_sessionmaker(
    bind=conexion,
    join_transaction_mode="create_savepoint",         # 2. commit() = liberar SAVEPOINT
    expire_on_commit=False,
)
app.dependency_overrides[get_db_session] = _sesion_de_test
...
await transaccion.rollback()                          # 3. se deshace todo
```

- Las peticiones de un test se ven entre sí.
- Una petición fallida revierte solo su SAVEPOINT.
- **Ningún test asume la base vacía**: pertenencia y `uuid4()` por test.

> Prohibido `TRUNCATE`, `DELETE`, `DROP`, bases aparte o commits con otro motor.

## 3. Fechas — propio de catering

El router usa `date.today()` como fecha de solicitud. Por eso:

- calendarios en **2099** → siempre hay ≥ 2 días de anticipación;
- calendarios en **2020** → `ANTICIPACION_INSUFICIENTE` garantizado;
- **2026** solo en `verificar-modificacion`, que recibe ambas fechas.

El guardián rechaza cualquier otro año.

## 4. Patrón

```python
async def test_marcar_dos_veces_sin_entrega_el_mismo_dia_devuelve_409(cliente):
    # Arrange
    calendario_id = await _crear_calendario(cliente)
    await cliente.patch(f"/calendarios/{calendario_id}/entregas/2099-01-05/sin-entrega", json={})

    # Act
    respuesta = await cliente.patch(f"/calendarios/{calendario_id}/entregas/2099-01-05/sin-entrega", json={})

    # Assert
    assert respuesta.status_code == 409
    assert respuesta.json()["tipo"] == "ENTREGA_NO_MODIFICABLE"
    calendario = (await cliente.get(f"/calendarios/{calendario_id}")).json()
    assert entrega_del(calendario, "2099-01-05")["estado"] == "SIN_ENTREGA"
```

Helpers: `cuerpo_calendario()`, `entrega_del()`, `DIRECCION_TRABAJO` (en
`test_calendarios_api_flujo_correcto.py`) y `_crear_calendario()` (en el de errores).

## 5. Mapa de errores a HTTP

| Situación | Status | `tipo` |
|---|---|---|
| `CalendarioNoEncontradoError` (comandos) | 404 | `CALENDARIO_NO_ENCONTRADO` |
| Calendario/paciente no encontrado en **lecturas** | 404 | *(sin `tipo`: `HTTPException` del router)* |
| `EntregaNoEncontradaError` | 404 | `ENTREGA_NO_ENCONTRADA` |
| `EntregaNoModificableError` | 409 | `ENTREGA_NO_MODIFICABLE` |
| `CalendarioInactivoError` | 409 | `CALENDARIO_INACTIVO` |
| `DireccionHabitualDuplicadaError` | 409 | `DIRECCION_HABITUAL_DUPLICADA` |
| `AnticipacionInsuficienteError` | 422 | `ANTICIPACION_INSUFICIENTE` |
| `FechaFueraDeRangoError` | 422 | `FECHA_FUERA_DE_RANGO` |
| Cuerpo / ruta inválidos | 422 | *(lista de errores de Pydantic)* |
| `DireccionHabitualNoEncontradaError`, `ValueError`, `MultipleResultsFound` | **500** | hallazgos: `pytest.raises(...)` |

## 6. Comandos

```powershell
docker compose up -d catering_db
uv run alembic upgrade head
uv run pytest tests/integration -v
uv run pytest tests/integration/test_convenciones_del_entorno.py -v   # guardián, sin Docker
```

Puerto 5433 reservado por Windows → `$env:CATERING_DB_PORT="55433"` y
`$env:TEST_DATABASE_URL="postgresql+asyncpg://postgres:password@localhost:55433/db_catering"`.

Conteo antes/después (debe coincidir):

```powershell
docker compose exec catering_db psql -U postgres -d db_catering -t -c "SELECT count(*) FROM calendarios_entrega;"
```

## 7. Postman

`postman/ms-catering.postman_collection.json` — `01 — Flujo correcto` (en orden)
y `02 — Flujo incorrecto`, 45 aserciones. **Sí escribe en la base.**

```bash
npx newman run postman/ms-catering.postman_collection.json -e postman/ms-catering.postman_environment.json
```

Si cambias un endpoint, actualiza pytest **y** la colección.

## 8. Errores frecuentes

- Meter un mock · asumir la base vacía · `TRUNCATE` "para limpiar".
- Verificar solo el status y no el `tipo`.
- Leer JSON de un 204: verifica con un `GET`.
- Fechas cercanas a hoy: el test caducará.
- BD levantada pero sin migrar: todo se omite; corre Alembic.
