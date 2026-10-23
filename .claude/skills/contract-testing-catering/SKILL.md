---
name: contract-testing-catering
description: Convenciones de contract testing con Pact (pact-python v3) en ms-catering — roles consumer/provider, mapa de relaciones con app-paciente y ms-pacientes, matchers para CalendarioResponse, provider states con SAVEPOINT sobre PostgreSQL, plantillas y problemas conocidos en Windows. Úsala al escribir, revisar o depurar cualquier archivo de tests/contract/ o pacts/, o al crear un adaptador HTTP hacia otro microservicio.
---

# Contract testing con Pact — ms-catering

Complementa `testing-catering` e `integration-testing-catering`.

## 1. Conceptos

| Concepto | Qué es | Dónde |
|---|---|---|
| **Consumer** | Hace la petición; **escribe** el contrato | `tests/contract/consumer/` |
| **Provider** | Responde; **verifica** el contrato | `tests/contract/provider/` |
| **Pact file** | JSON con las interacciones | `pacts/<consumer>-<provider>.json` |
| **Provider state** | Precondición (`given`) | `HANDLERS` en `app_provider.py` |
| **Matcher** | Regla de tipo/forma | `from pact import match` |

Contract = forma del mensaje. Integración = cableado interno. Unitaria = reglas.

## 2. Mapa de relaciones

```
app-paciente ──▶ ms-catering           pacts/app-paciente-ms-catering.json   ✅ verificado aquí
  (ClienteCalendarios)  GET /calendarios/{id}  ·  GET /calendarios/paciente/{id}  ·  404

ms-catering ───▶ ms-pacientes          pacts/ms-catering-ms-pacientes.json   ⏳ lo verifica ms-pacientes
  (PacienteGatewayHttp) GET /pacientes/{id}  ·  404
```

## 3. Plantilla consumer

```python
pytestmark = pytest.mark.contract
CONSUMER, PROVIDER = "app-paciente", "ms-catering"

@pytest.fixture(scope="module", autouse=True)
def _regenerar_contrato(carpeta_pacts):
    contrato_limpio(carpeta_pacts, CONSUMER, PROVIDER)

@pytest.fixture
def pact(carpeta_pacts):
    pact = Pact(CONSUMER, PROVIDER).with_specification("V4")
    yield pact
    pact.write_file(carpeta_pacts, overwrite=False)

async def test_<accion>_<condicion>_<resultado>(pact):
    # Arrange
    (pact.upon_receiving("descripción única")
        .given("existe un calendario activo", calendario_id=ID, paciente_id=PID)
        .with_request("GET", f"/calendarios/{ID}")
        .with_header("Accept", "application/json")
        .will_respond_with(200)
        .with_body({"id": match.uuid(ID)}, content_type="application/json"))

    with mock_server(pact) as servidor:
        # Act — siempre con el cliente real
        resultado = await ClienteCalendarios(servidor.url).obtener_calendario(UUID(ID))

    # Assert
    assert resultado["id"] == ID
```

### Matchers para esta API

| Campo | Matcher |
|---|---|
| UUID | `match.uuid(valor)` |
| `date` | `match.date("2099-01-01", "%Y-%m-%d")` (strftime) |
| `estado` del calendario | `match.regex("ACTIVO", regex=r"^(ACTIVO\|PAUSADO\|COMPLETADO\|CANCELADO)$")` |
| `estado` de la entrega | `match.regex("PROGRAMADA", regex=r"^(PROGRAMADA\|SIN_ENTREGA\|CANCELADA\|ENTREGADA)$")` |
| `bool` | `match.boolean(False)` |
| `int` | `match.integer(15)` |
| Lista | `match.each_like(elemento, min=1)` |

Los campos **nullable** (`referencia`, `zona`, `plan_nutricional_id`) deben
rellenarse en el estado del provider si el contrato usa un matcher de tipo.

## 4. Provider state

```python
async def _nombre_del_estado(session: AsyncSession, params: dict) -> None:
    # Construye el agregado por el CONSTRUCTOR (la factoría crear() genera un id nuevo
    # y el contrato fija el calendario_id) y guárdalo con el repositorio real.
    await CalendarioEntregaRepositoryImpl(session).guardar(calendario)

HANDLERS = {"nombre del estado": _nombre_del_estado}   # texto exacto del given(...)
```

Aislamiento en tres capas: transacción externa en el `lifespan` → SAVEPOINT por
interacción (`begin_nested()` / `rollback()`) → sesiones con `create_savepoint`.

## 5. Problemas conocidos

| Síntoma | Solución |
|---|---|
| `Missing request` aunque el cliente recibió 200 (Windows) | `mock_server(pact)` |
| `Host mismatch: 127.0.0.1 != localhost` | `Verifier(PROVIDER, host="127.0.0.1")` |
| Fecha que no casa con `yyyy-MM-dd` | `match.date(..., "%Y-%m-%d")` |
| `Provider state sin handler` (400) | Copia el texto exacto del `given` |
| `null` no casa con `match.string` | Rellena el campo en el handler del estado |
| Verificación omitida | BD sin migrar: `uv run alembic upgrade head` |

## 6. Comandos

```powershell
uv run pytest tests/contract/consumer -v
uv run pytest tests/contract/provider -v
uv run pytest tests/contract/test_convenciones_contrato.py -v
uv run pytest -m contract
```
