# DEMO — ms-catering (BC5)

Guion de demostración en vivo vía **Swagger** (`http://localhost:8020/docs`).

## Preparación

```bash
cd ms-catering
docker compose up -d
# → http://localhost:8020/docs
```

> Consejo: copia el `id` que devuelve el primer paso; se usa en todos los demás.
> Las fechas del guion son relativas: usa **hoy + 3 días** como `fecha_inicio` y **hoy + 17 días**
> como `fecha_fin`, para que quede margen frente a la regla de anticipación mínima (2 días).

---

## Paso 1 — Crear el calendario → `POST /calendarios`

```json
{
  "paciente_id": "11111111-1111-1111-1111-111111111111",
  "fecha_inicio": "2026-09-01",
  "fecha_fin": "2026-09-15",
  "direccion_inicial": {
    "direccion": "Av. Banzer 3er anillo #250",
    "referencia": "Edificio Torre Norte, piso 4",
    "zona": "Norte"
  }
}
```

Respuesta `201`. Guarda el `id` → **`CAL_ID`**.

Observa que el calendario nace con **una entrega por cada día del rango**, todas en estado
`PROGRAMADA` y con la dirección inicial. `total_dias` debe ser 15.

---

## Paso 2 — Ver las entregas generadas → `GET /calendarios/{CAL_ID}/entregas`

Devuelve las 15 entregas. Cada una con `fecha`, `estado`, `direccion` y `tiene_etiqueta`.

---

## Paso 3 — Registrar direcciones habituales → `POST /calendarios/{CAL_ID}/direcciones`

La dirección principal del paciente:

```json
{
  "nombre": "Casa",
  "direccion": {
    "direccion": "Av. Banzer 3er anillo #250",
    "referencia": "Edificio Torre Norte, piso 4",
    "zona": "Norte"
  },
  "es_principal": true
}
```

Y una segunda, para los días laborales:

```json
{
  "nombre": "Oficina",
  "direccion": {
    "direccion": "Calle Libertad #45",
    "referencia": "Frente a la plaza principal",
    "zona": "Centro"
  },
  "es_principal": false
}
```

Verifica con `GET /calendarios/{CAL_ID}/direcciones` — deben aparecer las dos.

---

## Paso 4 — Enviar un día a la oficina → `PATCH /calendarios/{CAL_ID}/entregas/{fecha}/direccion-habitual`

Usa una `fecha` dentro del rango del calendario:

```json
{ "nombre_direccion": "Oficina" }
```

Respuesta `204`. Vuelve a `GET /calendarios/{CAL_ID}/entregas` y comprueba que **solo esa** entrega
cambió de dirección; las demás siguen en "Casa".

---

## Paso 5 — Cambiar la dirección de un día puntual → `PATCH /calendarios/{CAL_ID}/entregas/{fecha}/direccion`

Una dirección de una sola vez, sin registrarla como habitual:

```json
{
  "nueva_direccion": {
    "direccion": "Hotel Los Tajibos, Av. San Martín #455",
    "referencia": "Recepción, dejar a nombre del paciente",
    "zona": "Equipetrol"
  }
}
```

---

## Paso 6 — Marcar un día sin entrega → `PATCH /calendarios/{CAL_ID}/entregas/{fecha}/sin-entrega`

```json
{ "motivo": "Paciente viaja fuera de la ciudad" }
```

Respuesta `204`. En `GET /calendarios/{CAL_ID}/entregas` esa entrega queda en estado de día sin
entrega y ya no es modificable.

---

## Paso 7 — Consultas operativas

- `GET /calendarios` → todos los calendarios activos.
- `GET /calendarios/paciente/{paciente_id}` → el calendario de un paciente.
- `GET /calendarios/entregas/fecha/{fecha}` → **la consulta del día para el equipo de reparto**:
  qué hay que entregar y en qué dirección en una fecha dada.

---

## Bonus — Reglas de negocio en vivo

Cada intento inválido devuelve un código HTTP distinto y un campo `tipo` que identifica la regla.

### B.1 — Anticipación mínima de 2 días → `422 ANTICIPACION_INSUFICIENTE`

Intenta cambiar la dirección de una entrega de **hoy o mañana**:

`PATCH /calendarios/{CAL_ID}/entregas/{fecha_de_mañana}/direccion`

```json
{ "nueva_direccion": { "direccion": "Cualquier calle #1" } }
```

Se rechaza: no hay margen para reprogramar el reparto.

Esta regla se puede consultar sin efectos secundarios:

`GET /calendarios/verificar-modificacion?fecha_entrega=2026-09-02&fecha_solicitud=2026-09-01`
→ `{ "puede_modificar": false, "dias_faltantes": 1 }`

### B.2 — Fecha fuera del rango del calendario → `422 FECHA_FUERA_DE_RANGO`

Usa una fecha posterior a `fecha_fin` en cualquiera de los `PATCH`. No existe entrega ese día.

### B.3 — Entrega ya no modificable → `409 ENTREGA_NO_MODIFICABLE`

Repite el paso 6 sobre la **misma** fecha ya marcada sin entrega: solo se modifican entregas en
estado `PROGRAMADA`.

### B.4 — Dirección habitual duplicada → `409 DIRECCION_HABITUAL_DUPLICADA`

Vuelve a enviar el `POST /calendarios/{CAL_ID}/direcciones` con `"nombre": "Casa"`. Los nombres de
las direcciones habituales son únicos por calendario.

### B.5 — Calendario inactivo → `409 CALENDARIO_INACTIVO`

Cancela el calendario y luego intenta modificar cualquier entrega:

```
DELETE /calendarios/{CAL_ID}        → 204
PATCH  /calendarios/{CAL_ID}/entregas/{fecha}/direccion   → 409
```

Sobre un calendario cancelado no se toca nada.

---

## Cierre

```bash
docker compose down       # agregar -v para borrar también los datos
```
