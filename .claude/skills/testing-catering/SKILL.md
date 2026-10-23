---
name: testing-catering
description: Convenciones de testing unitario de ms-catering — patrón AAA, naming en español, cómo doblar el puerto CalendarioEntregaRepository con AsyncMock, builders de calendario, reglas de anticipación y cómo medir cobertura con uv. Úsala al escribir, revisar o depurar cualquier test de tests/unit/.
---

# Convenciones de testing — ms-catering

Complementan `integration-testing-catering` (integración) y
`contract-testing-catering` (Pact).

## 1. Dónde va cada test

| Qué se prueba | Dónde | Qué doble se usa |
|---|---|---|
| VO, entidad, Aggregate Root, servicio de dominio | `tests/unit/domain/` | ninguno — objetos reales |
| Caso de uso / query handler | `tests/unit/application/` | `AsyncMock(spec=CalendarioEntregaRepository)` |
| Mapper, tabla excepción→HTTP, composición | `tests/unit/presentation/` | ninguno, **sin base de datos** |
| Gateways, repo en memoria, mapeo dominio↔ORM | `tests/unit/infrastructure/` | ninguno — sin red ni sesión |
| **Cuerpos** de endpoint y SQL del repositorio | `tests/integration/` | ninguno — PostgreSQL real |

La frontera la decide el **I/O**, no la capa. `_entrega_to_orm` vive en
`infrastructure/` pero construir un `EntregaORM` en memoria no abre sesión:
unitaria. `CalendarioEntregaRepositoryImpl.guardar` ejecuta SQL: integración.

**Prohibido en `tests/unit/`:** doblar `AsyncSession`, simular resultados de
SQLAlchemy o levantar un cliente HTTP.

## 2. AAA y naming

```python
def test_cambiar_direccion_fuera_del_rango_del_calendario_lanza_error(
    construir_calendario, direccion_trabajo
):
    # Arrange
    calendario = construir_calendario()

    # Act / Assert
    with pytest.raises(FechaFueraDeRangoError):
        calendario.cambiar_direccion_entrega(date(2026, 1, 16), direccion_trabajo, date(2025, 12, 1))
```

## 3. Fixtures (`tests/conftest.py`)

| Fixture / constante | Qué da |
|---|---|
| `construir_calendario(fecha_inicio, fecha_fin, estado, plan_nutricional_id)` | Calendario 2026-01-01 → 2026-01-15, ACTIVO, 15 entregas. `PAUSADO` se rehidrata por constructor |
| `direccion_domicilio` / `direccion_trabajo` | Dos `DireccionEntrega` válidas y distintas |
| `calendario_repo_mock` | `AsyncMock(spec=CalendarioEntregaRepository)` |
| `FECHA_SOLICITUD_VALIDA` | 2025-12-20: anticipación de sobra para todo el calendario |

## 4. Mocks — cheatsheet

| Necesito… | Cómo |
|---|---|
| Valor fijo | `calendario_repo_mock.obtener_por_id.return_value = calendario` |
| "No existe" | `... .return_value = None` |
| Verificar llamada | `... .assert_awaited_once_with(calendario.id)` |
| Verificar que no se persistió | `calendario_repo_mock.guardar.assert_not_awaited()` |
| Servicio síncrono | `Mock(spec=ValidadorCambioCalendarioService)` + `assert_called_once_with` |

`spec=` es obligatorio. Patrón de referencia:
`tests/unit/application/test_cambiar_direccion_entrega.py`.

## 5. Invariantes que conviene recordar

- Anticipación: `fecha_entrega - fecha_solicitud >= 2` días (2 es el límite **permitido**).
- Guardas en orden: ACTIVO → rango → anticipación → entrega existe → PROGRAMADA.
- `EntregaNoEncontradaError` solo es alcanzable con un calendario rehidratado al
  que le falta una entrega (la factoría genera todos los días).
- `cancelar_calendario` cancela solo las PROGRAMADAS.
- `registrar_direccion_habitual` **no** verifica que el calendario esté activo (hallazgo).
- Nombres de dirección habitual: comparación exacta.
- Las propiedades devuelven copias **superficiales**: la lista es nueva, las
  `Entrega` son las mismas instancias.

## 6. Comandos

```powershell
uv run pytest tests/unit -q
uv run pytest tests/unit/domain/test_calendario_entrega.py -v
uv run pytest tests/unit --cov --cov-report=term-missing `
    --cov-report=html:htmlcov-unit --cov-report=xml:coverage-unit.xml
Remove-Item .\htmlcov-unit\.gitignore
```

`fail_under = 80`; la medición oficial es `tests/unit` completo (~82 %). Ese
número incluye **cobertura de cableado** de infraestructura y presentación: no lo
presentes como si el repositorio estuviera probado.

## 7. Errores frecuentes

- `AsyncMock()` sin `spec` · `assert_called_once_with` en un `AsyncMock`.
- `date.today()` en un test.
- Cambiar el estado del calendario antes de prepararlo: un calendario no ACTIVO
  ya no admite cambios (por eso `construir_calendario` cambia el estado al final).
- Leer rutas de `app.routes`: en FastAPI 0.13x el router incluido queda envuelto;
  usa `app.openapi()["paths"]` o `calendarios.router.routes`.
- Escribir una "integración" con mocks: si hay un `AsyncMock`, va aquí.
