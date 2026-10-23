# Pruebas — ms-catering

Suite de pruebas del BC5 – Gestión de Catering. Aplica al caso de estudio los
tres talleres del módulo de testing, con la misma arquitectura que
`ms-plan-nutricional`:

- **Taller de Unit Tests** → `tests/unit/` — 198 tests, sin base de datos.
- **Taller de Integration Tests** → `tests/integration/` — 30 tests contra la API
  y PostgreSQL reales, más 14 que validan el propio entorno (sección 10).
- **Taller de Contract Testing (Pact)** → `tests/contract/` — 5 interacciones
  consumer, 1 verificación de provider y 12 tests que validan el entorno
  (sección 11).

**260 tests · 82 % de cobertura solo con las unitarias · 98 % con la suite
completa** (la sección 7 explica por qué son dos números y no uno).

---

## 1. Qué se prueba y qué no

| Capa | Pruebas unitarias | Pruebas de integración |
|---|---|---|
| `domain/` | **Sí** — 104 tests, con objetos reales | Indirectamente, a través de la API |
| `application/use_cases/` | **Sí** — 41 tests, repositorio mockeado | Indirectamente, a través de la API |
| `infrastructure/` — gateways, repo en memoria, mapeo ORM | **Sí** — 25 tests, sin red ni sesión | — |
| `infrastructure/` — repositorio SQLAlchemy | No — requiere PostgreSQL | **Sí** — `guardar`/consultas reales, `commit`/`rollback` |
| `presentation/` — mapper, excepciones, composición | **Sí** — 28 tests, sin HTTP ni base de datos | — |
| `presentation/` — cuerpos de endpoint | No — es la frontera HTTP | **Sí** — router, `Depends` y errores en petición real |

**Cada capa se prueba con la herramienta que le corresponde.** Las reglas de
negocio se verifican una sola vez, en las unitarias; las de integración no las
repiten, sino que comprueban el *cableado* entre capas, que es justo lo que un
mock oculta.

Lo que decide la frontera no es la capa, sino el **I/O**. Las funciones de mapeo
dominio↔ORM viven en `infrastructure/`, pero construir una instancia ORM en
memoria no abre ninguna sesión: son funciones puras y se prueban como unitarias
(`test_mapeo_orm.py`). Los métodos del repositorio que ejecutan SQL, no.

---

## 2. Cómo ejecutar

```bash
uv sync                                   # dev + test

uv run pytest -q                          # toda la suite
uv run pytest tests/unit -q               # solo unitarias
uv run pytest -m integration -v           # solo integración
uv run pytest -m contract -v              # solo contratos
uv run pytest tests/unit/domain/test_calendario_entrega.py -v
uv run pytest -k "anticipacion" -v
```

> **Las unitarias no necesitan PostgreSQL.** Con la base apagada, `uv run pytest`
> reporta `229 passed, 31 skipped`: las de integración y la verificación del
> provider se omiten, no fallan.

La integración y la verificación del provider necesitan la BD **con el esquema
aplicado** (lo crea Alembic, no el docker-compose):

```bash
docker compose up -d catering_db
uv run alembic upgrade head
```

> **Trampa de Windows:** Hyper-V/WinNAT puede reservar un rango de puertos que
> incluya el 5433 (`netsh int ipv4 show excludedportrange protocol=tcp`). Si
> `docker compose up` falla con *"An attempt was made to access a socket in a way
> forbidden"*, mueve el puerto sin tocar archivos:
>
> ```powershell
> $env:CATERING_DB_PORT = "55433"
> docker compose up -d catering_db
> $env:DATABASE_URL = "postgresql+asyncpg://postgres:password@localhost:55433/db_catering"
> uv run alembic upgrade head
> $env:TEST_DATABASE_URL = $env:DATABASE_URL
> uv run pytest
> ```

---

## 3. Estructura

```
tests/
├── conftest.py                       # fixtures de las UNITARIAS (builders + mock del puerto)
├── unit/
│   ├── domain/                       # espeja src/catering/domain/
│   │   ├── test_value_objects.py     # DireccionEntrega, AnticipacionMinima, DiaSinEntrega, Etiqueta
│   │   ├── test_entrega.py           # Entrega y DireccionHabitual
│   │   ├── test_calendario_entrega.py   # Aggregate Root: HU-26/27/28/30 y ciclo de vida
│   │   └── test_catering_services.py    # ValidadorCambioCalendarioService
│   ├── application/                  # un archivo por caso de uso + query handlers
│   ├── presentation/                 # solo lo que NO hace I/O
│   │   ├── test_mappers.py
│   │   ├── test_exception_handlers.py
│   │   └── test_composicion_de_la_app.py
│   └── infrastructure/
│       ├── test_paciente_gateway_mock.py
│       ├── test_calendario_repository_mock.py
│       └── test_mapeo_orm.py
├── integration/                      # se organiza por flujo, no por capa
│   ├── conftest.py                   # motor, transacción reversible y cliente HTTP
│   ├── test_calendarios_api_flujo_correcto.py
│   ├── test_calendarios_api_flujo_incorrecto.py
│   └── test_convenciones_del_entorno.py   # guardián (sección 10.5)
└── contract/                         # se organiza por rol
    ├── conftest.py                   # carpeta pacts/, contrato_limpio, mock_server
    ├── consumer/
    │   ├── cliente_calendarios.py                  # cliente de "app-paciente"
    │   ├── test_app_paciente_consume_calendarios.py  # 3 interacciones
    │   └── test_catering_consume_pacientes.py        # 2 interacciones
    ├── provider/
    │   ├── app_provider.py                         # app real + provider states
    │   └── test_verificar_calendarios_provider.py
    └── test_convenciones_contrato.py               # guardián (sección 11.5)
```

`tests/conftest.py` centraliza lo que se repetiría en cada unitaria:

- **Builders de dominio** — `construir_calendario()`, `direccion_domicilio`,
  `direccion_trabajo`. Varían solo lo que interesa:
  `construir_calendario(estado=EstadoCalendario.CANCELADO, plan_nutricional_id=uuid4())`.
- **Constantes de fecha** — `FECHA_INICIO`, `FECHA_FIN` y `FECHA_SOLICITUD_VALIDA`
  (con anticipación de sobra para cualquier día del calendario por defecto).
- **Mock del puerto** — `calendario_repo_mock = AsyncMock(spec=CalendarioEntregaRepository)`.

---

## 4. Qué es un mock y por qué se usa aquí

Los casos de uso reciben el repositorio por **inyección de dependencias**:

```python
class CambiarDireccionEntregaUseCase:
    def __init__(self, repo: CalendarioEntregaRepository) -> None:
        self._repo = repo
```

El repositorio real habla con PostgreSQL. Un **mock** ocupa su lugar y permite:

```python
calendario_repo_mock.obtener_por_id.return_value = calendario      # controlar la entrada
calendario_repo_mock.guardar.assert_awaited_once_with(calendario)  # verificar la salida
```

`spec=` es obligatorio: sin él, `repo.obtner_por_id()` devolvería otro mock y el
test pasaría en verde ocultando el error
(`test_el_mock_con_spec_rechaza_metodos_que_no_existen_en_el_puerto`).

**Regla del camino de error:** todo test que comprueba un error afirma además que
no se persistió nada:

```python
with pytest.raises(CalendarioNoEncontradoError):
    await caso_de_uso.ejecutar(cmd)

calendario_repo_mock.guardar.assert_not_awaited()
```

| Necesito… | Cómo |
|---|---|
| Que devuelva un valor fijo | `mock.metodo.return_value = calendario` |
| Que devuelva "no existe" | `mock.metodo.return_value = None` |
| Que lance una excepción | `mock.metodo.side_effect = ErrorDeDominio(...)` |
| Verificar una llamada exacta | `mock.metodo.assert_awaited_once_with(id)` |
| Verificar que NO se llamó | `mock.metodo.assert_not_awaited()` |
| Contar llamadas | `mock.metodo.await_count == 2` |
| Doblar un servicio **síncrono** | `Mock(spec=ValidadorCambioCalendarioService)` + `assert_called_once_with` |

Patrón de referencia: `tests/unit/application/test_cambiar_direccion_entrega.py`.

---

## 5. Patrón AAA y convención de nombres

Cada test tiene tres bloques `# Arrange` / `# Act` / `# Assert` (fusionados en
`# Act / Assert` cuando coinciden en un `pytest.raises`). Los nombres siguen
`test_<accion>_<condicion>_<resultado_esperado>`, en español, para que la salida
de pytest se lea como una especificación:

```python
def test_cambiar_direccion_sin_dos_dias_de_anticipacion_lanza_error_y_no_cambia_nada(...):
```

Las variantes del mismo comportamiento se agrupan con `@pytest.mark.parametrize`
(los tres estados inactivos, las fechas límite de la anticipación, etc.).

**Fechas fijas siempre** (`date(2026, 1, 1)`), nunca `date.today()`.

---

## 6. Inventario de la suite

### Capa unitaria — 198 tests

| Archivo | Tests | Qué cubre |
|---|---|---|
| `unit/domain/test_calendario_entrega.py` | 56 | Factoría, copias defensivas, HU-26/27/28/30, orden de las guardas, ciclo de vida |
| `unit/domain/test_value_objects.py` | 22 | Validación de dirección, regla de 2 días con sus límites, inmutabilidad |
| `unit/domain/test_entrega.py` | 16 | Entidad `Entrega` (estado modificable, mutaciones) y `DireccionHabitual` |
| `unit/domain/test_catering_services.py` | 10 | `puede_modificar` y `dias_restantes_para_modificar`, coherentes entre sí |
| **Subtotal dominio** | **104** | |
| `unit/application/` — 7 archivos | 41 | 6 casos de uso + 5 query handlers: camino feliz y **todas** las ramas de error con `guardar.assert_not_awaited()` |
| `unit/presentation/test_exception_handlers.py` | 13 | Tabla excepción → `(status, tipo)` y red de seguridad de manejadores |
| `unit/presentation/test_mappers.py` | 8 | `calendario_to_response`: aplanado del VO, enums a texto, campos no publicados |
| `unit/presentation/test_composicion_de_la_app.py` | 7 | Endpoints del contrato, OpenAPI, orden de rutas, inyección por puerto, engine |
| `unit/infrastructure/test_mapeo_orm.py` | 10 | Ida y vuelta dominio↔ORM, restricciones del esquema, `lazy="raise"` |
| `unit/infrastructure/test_calendario_repository_mock.py` | 8 | Repositorio en memoria (almacén compartido) |
| `unit/infrastructure/test_paciente_gateway_mock.py` | 7 | Gateways de pacientes: determinismo y cumplimiento del puerto |

### Capa de integración — 44 tests

| Archivo | Tests | Qué cubre |
|---|---|---|
| `integration/test_calendarios_api_flujo_incorrecto.py` | 19 | 404 / 409 / 422 con su `tipo`, ausencia de escritura tras el fallo, y 3 hallazgos |
| `integration/test_convenciones_del_entorno.py` | 14 | Guardián: mocks, borrados, aislamiento, naming, fechas, Postman |
| `integration/test_calendarios_api_flujo_correcto.py` | 11 | Ciclo de vida completo, consolidado HU-29, verificación HU-28, aislamiento |

### Capa de contrato — 18 tests

| Archivo | Tests |
|---|---|
| `contract/consumer/test_app_paciente_consume_calendarios.py` | 3 |
| `contract/consumer/test_catering_consume_pacientes.py` | 2 |
| `contract/provider/test_verificar_calendarios_provider.py` | 1 |
| `contract/test_convenciones_contrato.py` | 12 |

**Total: 260 tests.**

---

## 7. Cobertura

### 7.1 Reporte oficial — solo unitarias

```powershell
uv run pytest tests/unit --cov --cov-report=term-missing `
    --cov-report=html:htmlcov-unit --cov-report=xml:coverage-unit.xml
Remove-Item .\htmlcov-unit\.gitignore    # coverage.py lo recrea con "*"
```

No necesita PostgreSQL. Resultado: **82 %** (820 statements + 78 ramas).
`domain/` y `application/` están al 100 %. Lo que queda fuera por definición son
los cuerpos de los endpoints, el SQL del repositorio, `get_db_session`, el
`lifespan` y la petición HTTP de `PacienteGatewayHttp`.

### 7.2 Suite completa

```bash
uv run pytest --cov --cov-report=term-missing --cov-report=html:htmlcov
```

Con integración y contrato ejecutándose: **98 %**. `calendario_repository_impl.py`
pasa a 93 % y `routers/calendarios.py` a 98 %.

### 7.3 Dos trampas de medición

- **Cobertura de cableado vs. de comportamiento.** Importar `presentation.api.main`
  arrastra router, repositorio, ORM y esquemas, y sus líneas de módulo cuentan como
  cubiertas. Los tests de `test_composicion_de_la_app.py` afirman ese cableado,
  pero el comportamiento del repositorio y de los endpoints solo lo prueban las de
  integración. No presentes el 82 % como si el repositorio estuviera probado.
- **`concurrency = ["greenlet", "thread"]` es obligatorio** en `pyproject.toml`.
  SQLAlchemy asyncio reanuda el código tras cada `await session.execute()` dentro
  de un greenlet; sin declararlo, coverage.py deja de trazar esas líneas y el
  repositorio aparecía al 38 % aunque la integración lo recorre entero.

### 7.4 Umbral

`fail_under = 80` se aplica a **cualquier** invocación con `--cov`: medir una
subcarpeta suelta fallará aunque sus tests pasen. La medición oficial es
`tests/unit` completo. `htmlcov-unit/` y `coverage-unit.xml` **se versionan**:
son el entregable.

---

## 8. Hallazgos

Las pruebas revelaron comportamientos que no coinciden con las historias de
usuario. Salvo el primero, **no se modificó `src/`**: cada uno tiene un test que
fija el comportamiento actual y lo documenta en su docstring. Si se corrige, ese
test fallará y habrá que actualizarlo a propósito.

### 8.1 Corregido — toda modificación del calendario respondía 500

**Síntoma.** `PATCH .../direccion` (HU-26), `PATCH .../sin-entrega` (HU-27),
`POST .../direcciones` y `PATCH .../direccion-habitual` (HU-30) y
`DELETE /calendarios/{id}` respondían **500** con `MissingGreenlet`. Solo crear y
consultar funcionaban — es decir, el paciente no podía gestionar su servicio, que
es la responsabilidad que el documento del caso de estudio asigna a ms-catering.
Ninguna unitaria podía verlo: el mock del repositorio no ejecuta `guardar()`.

**Causa.** `guardar()` buscaba la fila con `session.get()` y luego recorría
`existing.entregas`. La fila que había leído `obtener_por_id` ya se había
traducido a dominio y el identity map (de referencias débiles) la había soltado;
`get()` volvía a la base **sin colecciones**, y acceder a ellas disparaba una carga
perezosa, que con `AsyncSession` no puede hacer I/O.

**Corrección** (siguiendo la guía *Preventing Implicit IO when Using
AsyncSession* de SQLAlchemy 2.0):

1. `guardar()` recarga el agregado completo con `select(...).options(*_EAGER)`: el
   agregado se lee y se escribe entero, porque es la frontera de consistencia.
2. `_EAGER` usa `selectinload` en vez de `joinedload`: tres JOIN sobre
   colecciones multiplicaban filas (entregas × direcciones × días sin entrega).
3. Las tres colecciones de `CalendarioEntregaORM` declaran `lazy="raise"`: un
   olvido futuro falla en el acto con un error explícito en vez de un 500 opaco.

**Regresión cubierta por** el flujo correcto de integración, el Postman, y
`test_las_colecciones_del_agregado_prohiben_la_carga_perezosa_implicita`.

> La corrección viaja en la imagen `betonavarro/ms-catering:0.1.1`, a la que apunta
> `docker-compose.yml` (la `0.1.0` es anterior). Verificada con el stack completo:
> la colección de Postman pasa 45/45 contra el contenedor en el puerto 8020.

### 8.2 Pendientes (documentados, sin corregir)

| # | Hallazgo | Efecto | Test que lo fija |
|---|---|---|---|
| 1 | `DireccionHabitualNoEncontradaError` no tiene manejador | HU-30 con un nombre no registrado → 500 en vez de 404 | `test_direccion_habitual_no_encontrada_no_tiene_manejador_y_acaba_en_500` · `test_asignar_una_direccion_habitual_inexistente_escapa_sin_manejador_http` |
| 2 | No hay manejador de `ValueError` | Dirección vacía → 500 (plan-nutricional responde 422 `VALOR_INVALIDO`) | `test_un_value_error_del_dominio_no_tiene_manejador_y_acaba_en_500` · `test_crear_calendario_con_direccion_vacia_escapa_como_value_error` |
| 3 | Se pueden crear dos calendarios ACTIVOS para el mismo paciente | `GET /calendarios/paciente/{id}` (HU-25) → `MultipleResultsFound` → 500 | `test_crear_calendario_no_verifica_si_el_paciente_ya_tiene_uno_activo` · `test_dos_calendarios_activos_del_mismo_paciente_rompen_la_consulta_por_paciente` |
| 4 | `crear()` no valida `fecha_fin >= fecha_inicio` | Calendario sin entregas en el dominio; la BD lo rechaza con un CHECK → 500 | `test_crear_con_fin_anterior_al_inicio_no_lanza_error_y_genera_cero_entregas` |
| 5 | `registrar_direccion_habitual` no llama a `_verificar_activo()` | Se pueden registrar direcciones en un calendario cancelado | `test_registrar_direccion_habitual_en_un_calendario_cancelado_esta_permitido` |
| 6 | La `Etiqueta` se escribe en el ORM pero no se reconstruye al leer | `tiene_etiqueta` siempre `False` tras leer de la base | `test_la_etiqueta_se_escribe_en_el_orm_pero_no_se_reconstruye_al_leer` |
| 7 | `Entrega` no valida sus transiciones | Una entrega cancelada puede marcarse entregada (hoy no expuesto) | `test_una_entrega_cancelada_puede_marcarse_entregada_porque_la_entidad_no_valida` |

---

## 9. Entorno de pruebas para IA

| Pieza | Unitarias | Integración | Contrato |
|---|---|---|---|
| **Subagente** — *quién* | `.claude/agents/test-writer.md` | `.claude/agents/integration-test-writer.md` | `.claude/agents/pact-writer.md` |
| **Skill** — *cómo* | `.claude/skills/testing-catering/` | `.claude/skills/integration-testing-catering/` | `.claude/skills/contract-testing-catering/` |
| **Guardián** — *quién lo comprueba* | — | `test_convenciones_del_entorno.py` (14) | `test_convenciones_contrato.py` (12) |

Los alcances no se solapan: el `test-writer` no toca `tests/integration/`,
`tests/contract/` ni `postman/`; el `integration-test-writer` no toca `tests/unit/`
ni `tests/conftest.py`; el `pact-writer` solo `tests/contract/`, `pacts/` y los
adaptadores HTTP. Ninguno puede modificar `src/` para hacer pasar un test, añadir
`# pragma: no cover` ni relajar un guardián.

---

## 10. Pruebas de integración

### 10.1 Qué cambia respecto a una unitaria

|  | Unitaria | Integración |
|---|---|---|
| Dobles de prueba | `AsyncMock(spec=Puerto)` | **Ninguno** |
| Base de datos | No se usa | PostgreSQL real |
| Punto de entrada | El caso de uso, en Python | Una petición HTTP |
| Qué demuestra | Que la **regla de negocio** es correcta | Que el **cableado** entre capas funciona |

```
HTTP → router → caso de uso → repositorio SQLAlchemy → PostgreSQL → HTTP
```

### 10.2 Los dos flujos

**Flujo correcto** — un test largo, deliberadamente: partirlo rompería lo que se
quiere demostrar, que el estado sobrevive de una petición a la siguiente.

```
POST   /calendarios                                    → 201  15 entregas PROGRAMADAS
GET    /calendarios/{id}                               → 200
PATCH  /calendarios/{id}/entregas/2099-01-03/direccion → 204  + GET: solo cambió ese día
POST   /calendarios/{id}/direcciones   {trabajo}       → 204  + GET direcciones
PATCH  /calendarios/{id}/entregas/2099-01-06/direccion-habitual → 204
PATCH  /calendarios/{id}/entregas/2099-01-10/sin-entrega        → 204
GET    /calendarios/paciente/{paciente_id}             → 200
DELETE /calendarios/{id}                               → 204  + GET: cascada correcta
```

**Flujo incorrecto:**

| Escenario | Respuesta |
|---|---|
| Calendario / paciente / entregas inexistentes | 404 |
| Modificar o cancelar un calendario inexistente | 404 `CALENDARIO_NO_ENCONTRADO` |
| Marcar dos veces el mismo día · cambiar un día sin entrega | 409 `ENTREGA_NO_MODIFICABLE` |
| Modificar o re-cancelar un calendario cancelado | 409 `CALENDARIO_INACTIVO` |
| Dirección habitual duplicada | 409 `DIRECCION_HABITUAL_DUPLICADA` |
| Cambio sin 2 días de anticipación (HU-28) | 422 `ANTICIPACION_INSUFICIENTE` |
| Fecha fuera del calendario | 422 `FECHA_FUERA_DE_RANGO` |
| Sin `paciente_id` · fecha o UUID mal formados | 422 de Pydantic |

Cada camino de error termina releyendo el recurso: es el equivalente integrado de
`guardar.assert_not_awaited()`, y prueba de verdad que el `rollback` funciona.

### 10.3 Las fechas y la regla de los 2 días

Los endpoints de modificación usan `date.today()` como fecha de solicitud (el
cliente no la envía). Para que ningún test dependa del día en que se ejecuta, los
calendarios de integración están en **2099** (siempre modificables) o en **2020**
(nunca). El guardián lo exige (`test_los_calendarios_de_prueba_estan_en_fechas_lejanas_al_presente`).

### 10.4 Cómo se montan (`tests/integration/conftest.py`)

1. **Una sola base, y no se ensucia.** Se usa `db_catering`, la de desarrollo.
   Cada test corre dentro de una transacción externa; las sesiones de la app usan
   `join_transaction_mode="create_savepoint"`, así que su `commit()` solo libera un
   SAVEPOINT, y al final un `rollback()` lo deshace todo. Los tests
   `test_aislamiento_paso_1_*` y `test_aislamiento_paso_2_*` lo demuestran.
2. **Un solo punto de inyección:** `app.dependency_overrides[get_db_session]`.
3. **Sin uvicorn:** `httpx.AsyncClient` + `ASGITransport`.
4. **Skip limpio:** si PostgreSQL no responde **o no está migrado**, `comprobar_bd`
   hace `pytest.skip`.

**Comprobar que no ensucian:**

```powershell
docker compose exec catering_db psql -U postgres -d db_catering -t -c "SELECT count(*) FROM calendarios_entrega;"
uv run pytest tests/integration -q
docker compose exec catering_db psql -U postgres -d db_catering -t -c "SELECT count(*) FROM calendarios_entrega;"
```

### 10.5 Postman

`postman/ms-catering.postman_collection.json`: `01 — Flujo correcto` (13
peticiones dependientes, ejecutar en orden) y `02 — Flujo incorrecto` (14), con 45
aserciones `pm.test`. **Sí escribe en la base**: va por la red y no puede
envolverse en una transacción. Cada corrida usa un `paciente_id` nuevo (`{{$guid}}`).

```bash
uv run fastapi dev main.py
npx newman run postman/ms-catering.postman_collection.json -e postman/ms-catering.postman_environment.json
```

---

## 11. Contract testing con Pact

### 11.1 Relaciones cubiertas

```
app-paciente ──────▶ ms-catering        ✅ verificado en este repo
  GET /calendarios/{id}                → 200 (calendario con entregas y direcciones)
  GET /calendarios/paciente/{id}       → 200 (calendario activo del paciente, HU-25)
  GET /calendarios/{id}                → 404

ms-catering ───────▶ ms-pacientes       ⏳ lo verifica el equipo de ms-pacientes
  GET /pacientes/{id}                  → 200 (datos de la Etiqueta)
  GET /pacientes/{id}                  → 404 (PacienteNoEncontradoError)
```

- `app-paciente` es un consumer simulado; su cliente es `ClienteCalendarios`.
- En la segunda relación ms-catering es el consumer: el contrato sale del adaptador
  real `PacienteGatewayHttp` (`src/catering/infrastructure/gateways/`), añadido
  para este taller.

### 11.2 Cómo se verifica el provider sin ensuciar la base

`tests/contract/provider/app_provider.py` monta la app real dentro de una app de
verificación con una transacción externa (revertida al apagar uvicorn) y la ruta
`POST /_pact/provider-states`, que abre un SAVEPOINT por interacción y lo revierte
en el `teardown`. Esa ruta **nunca** existe en `src/` (el guardián lo vigila).

### 11.3 Cómo ejecutar

```bash
uv run pytest tests/contract/consumer -v                       # 1. genera pacts/
uv run pytest tests/contract/provider -v                       # 2. verifica (requiere PostgreSQL)
uv run pytest tests/contract/test_convenciones_contrato.py -v  # 3. guardián (sin Docker)
```

**Prueba negativa.** Si el consumer pasa a esperar `total_dias_contratados` en vez
de `total_dias`, la verificación falla con:

```
$ -> Actual map is missing the following keys: total_dias_contratados
```

### 11.4 Problemas conocidos

- **Falso `Missing request` en Windows** → usar `mock_server(pact)`, nunca `pact.serve()`.
- **`match.date` usa formato strftime** (`%Y-%m-%d`).
- **`Verifier` usa `localhost`** → `Verifier(PROVIDER, host="127.0.0.1")`.
- **Campos opcionales:** `referencia`, `zona` y `plan_nutricional_id` pueden ser
  `null`; el estado del provider los crea con valor para que los matchers de tipo
  apliquen.
