# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Qué es esto

`ms-catering` — microservicio del BC5 (Gestión de Catering) del sistema NUR-TRICENTER. FastAPI + SQLAlchemy async + PostgreSQL, esquema versionado con Alembic, Python >= 3.12, gestionado con **uv** (no pip, no poetry).

La documentación del proyecto está en español y los nombres de test también. Mantén ese idioma.

## Comandos

```bash
uv sync                                              # instalar (grupos dev + test)

docker compose up -d catering_db                     # solo la BD
uv run alembic upgrade head                          # el esquema lo crea Alembic, no el compose
uv run fastapi dev main.py                           # API en el host → :8000, docs en /docs
docker compose up -d                                 # stack completo (API en 8020-8022, imagen publicada)

uv run pytest -q                                     # suite completa
uv run pytest tests/unit -q                          # unitarias (no necesitan BD)
uv run pytest -m integration -v                      # integración (necesita BD migrada)
uv run pytest -m contract -v                         # contratos Pact
uv run pytest -k "anticipacion" -v                   # filtrar por nombre
```

Cobertura — hay **dos** mediciones y no son intercambiables:

```bash
# OFICIAL (requisito del taller, >= 80 %): capa unitaria, sin BD. Da ~82 %.
uv run pytest tests/unit --cov --cov-report=term-missing \
    --cov-report=html:htmlcov-unit --cov-report=xml:coverage-unit.xml

# Suite completa con PostgreSQL levantado. Da ~98 %.
uv run pytest --cov --cov-report=term-missing --cov-report=html:htmlcov
```

No hay linter ni formateador configurados.

## Trampas del entorno

- **La BD escucha en el 5433.** Si Windows lo tiene reservado (Hyper-V), muévelo sin tocar archivos: `CATERING_DB_PORT=55433` para el compose y `DATABASE_URL` / `TEST_DATABASE_URL` apuntando a ese puerto.
- **BD levantada pero sin migrar** → las pruebas de integración se omiten (skip); corre `uv run alembic upgrade head`.
- **Cobertura en 0 %** → falta la instalación editable: `uv sync`.
- **`concurrency = ["greenlet", "thread"]`** en `[tool.coverage.run]` es obligatorio: sin él, las líneas tras cada `await session.execute()` no se trazan.
- **`fail_under = 80` aplica a cualquier invocación con `--cov`**; la medición oficial es `tests/unit` completo.
- **Al regenerar `htmlcov-unit/`** borra el `htmlcov-unit/.gitignore` que coverage.py recrea con `*`.
- **Imagen vigente: `betonavarro/ms-catering:0.1.1`** (incluye la corrección de `guardar()`, tests/README.md §8.1); la `0.1.0` no. Si cambias `src/`, reconstruye con un tag nuevo y actualiza `docker-compose.yml`. El `Dockerfile` excluye el grupo `test`.
- **FastAPI 0.13x** ya no expone las rutas de un router incluido en `app.routes`: usa `app.openapi()["paths"]` o `calendarios.router.routes`.

## Arquitectura

Clean Architecture + DDD + CQRS ligero. Dependencias hacia adentro: `presentation → application → domain`. El dominio es Python puro.

```
src/catering/
├── domain/          model/ (AR CalendarioEntrega + Entrega, DireccionHabitual, VOs, enums), exceptions/, repositories/ (puerto ABC), services/, gateways/
├── application/     commands/ y queries/ (dataclasses frozen), use_cases/ (una clase por caso de uso)
├── infrastructure/  persistence/ (ORM, repo SQLAlchemy, repo en memoria), config/, gateways/ (mock + HTTP de pacientes)
└── presentation/    api/routers/calendarios.py, api/schemas/ (Pydantic + mapper), main.py (manejadores de excepción)
```

**Forma canónica de un caso de uso:** `obtener_por_id` → si `None`, `CalendarioNoEncontradoError` → método de dominio → `guardar`.

**El agregado se carga y se guarda completo.** Las colecciones de `CalendarioEntregaORM` son `lazy="raise"`; toda lectura pasa por `_EAGER` (`selectinload`). Nunca uses `session.get()` para el agregado.

**Inyección:** `_get_repo` del router anota el **puerto** (`CalendarioEntregaRepository`), no la implementación — hay un test que lo vigila. Depende de `get_db_session`, la hoja donde las pruebas de integración inyectan su sesión. `get_db_session` hace `commit` al salir y `rollback` ante excepción.

**Errores → HTTP:** manejadores en `presentation/api/main.py` con `{"detail", "tipo"}`. 404 `*NoEncontrado*`, 409 `EntregaNoModificable` / `CalendarioInactivo` / `DireccionHabitualDuplicada`, 422 `AnticipacionInsuficiente` / `FechaFueraDeRango`. Si añades una excepción de dominio, añade su manejador: hay un test que lo exige (con `DireccionHabitualNoEncontradaError` como hueco conocido y documentado).

## Invariantes de negocio que conviene saber de memoria

- **Anticipación mínima: 2 días** (`fecha_entrega - fecha_solicitud >= 2`). El router usa `date.today()` como fecha de solicitud.
- Orden de las guardas al modificar un día: calendario ACTIVO → fecha en rango → anticipación → entrega existe → entrega PROGRAMADA.
- Solo una entrega `PROGRAMADA` es modificable.
- `cancelar_calendario` cancela en cascada solo las `PROGRAMADA` (respeta `SIN_ENTREGA` y `ENTREGADA`).
- `PAUSADO` no tiene método de dominio: solo llega por rehidratación.
- Nombres de dirección habitual: comparación **exacta** (distingue mayúsculas).
- La factoría `crear()` genera una entrega por día; el constructor (rehidratación) no valida. Es deliberado.

## Testing

Antes de escribir cualquier test, carga la skill correspondiente: `testing-catering` (unitarias), `integration-testing-catering` (integración) o `contract-testing-catering` (Pact).

- **AAA** con `# Arrange` / `# Act` / `# Assert` (`# Act / Assert` en un `pytest.raises`).
- Nombres en español: `test_<accion>_<condicion>_<resultado_esperado>`.
- `asyncio_mode = "auto"`: los tests `async def` **no** llevan decorador.
- Dobles: **siempre** `AsyncMock(spec=CalendarioEntregaRepository)` (fixture `calendario_repo_mock`); `Mock(spec=...)` para el servicio síncrono.
- `assert_awaited_once_with`, nunca `assert_called_once_with` en un `AsyncMock`.
- Cada rama de error cierra con `calendario_repo_mock.guardar.assert_not_awaited()`.
- Fechas fijas. En unitarias `date(2026, 1, …)` con `FECHA_SOLICITUD_VALIDA`; en integración calendarios en **2099** (modificables) o **2020** (nunca) — el guardián lo exige.

| Qué | Dónde |
|---|---|
| Dominio, casos de uso | `tests/unit/domain/`, `tests/unit/application/` |
| Mapper, tabla excepción→HTTP, composición | `tests/unit/presentation/` |
| Gateways, repo en memoria, mapeo dominio↔ORM | `tests/unit/infrastructure/` |
| Cuerpos de endpoint, SQL del repositorio | `tests/integration/` |
| Forma de los mensajes entre servicios | `tests/contract/` |

Prohibido en `tests/unit/`: doblar `AsyncSession`, simular resultados de SQLAlchemy, levantar un cliente HTTP.

**Reglas duras de `tests/integration/`:** cero mocks; ningún test asume BD vacía; nada de `TRUNCATE`/`DELETE`/`DROP`; aislamiento por transacción reversible (`create_savepoint`) en la fixture `cliente`. `test_convenciones_del_entorno.py` es el guardián (14 tests) — nunca lo relajes.

Si cambias un endpoint, actualiza también `postman/ms-catering.postman_collection.json` y, si lo consume otro servicio, el contrato Pact.

## Restricciones

- **No modifiques `src/` para hacer pasar un test.** Si un test revela un bug, escribe un test que documente el comportamiento actual y dilo (tests/README.md §8 lista los pendientes).
- No uses `# pragma: no cover` ni bajes `fail_under`.
- Los subagentes `test-writer`, `integration-test-writer` y `pact-writer` tienen alcances que no se solapan; respétalos.
