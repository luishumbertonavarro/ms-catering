# Eventos de integración — ms-catering (BC5)

**Sistema:** NUR-TRICENTER · **Responsable:** Luis Humberto Navarro Ribeiro
**Estado:** implementado (outbox + RabbitMQ). Contratos finales en `Eventos_Integracion_NUR-TRICENTER.docx`. Los eventos que este servicio
**produce** salen de su código actual (agregado `CalendarioEntrega`); los que
**consume** son una propuesta que debe confirmar el equipo que los produce.

> **Evento de integración** = algo que **ya pasó** en este microservicio y que le
> interesa a **otro** microservicio. Lo que solo le interesa a BC5 (registrar una
> dirección habitual con nombre) es un evento de **dominio** y no se publica: ver la
> [sección 5](#5-eventos-de-dominio-que-no-se-publican).

---

## 1. Convenciones del grupo (implementadas)

> Esta sección reemplaza la propuesta original del sobre `{evento_id, tipo, datos…}`.
> Lo acordado en `Eventos_Integracion_NUR-TRICENTER.docx` y lo que corre hoy es:

| Aspecto | Convención |
|---|---|
| Broker | **RabbitMQ**, exchange **topic** durable `nurtricenter.events` |
| Routing key | `entidad.participio` en minúsculas: `plan_nutricional.creado`, `calendario.cancelado`, `servicio.contratado` |
| Cuerpo | El JSON del evento **directo, sin sobre** (los bloques «datos» de este documento son el cuerpo completo) |
| Metadatos | Propiedades AMQP: `message_id` (id de la fila del outbox, para idempotencia), `type` (nombre del evento en PascalCase), `timestamp`, `content_type=application/json`, `delivery_mode=persistent` |
| Colas | Una cola durable por microservicio: `ms-plan-nutricional.eventos`, `ms-catering.eventos` |
| Formatos | Ids UUID en texto, fechas `YYYY-MM-DD`, decimales como texto (`"2000.00"`). Los consumidores aceptan camelCase (productores .NET) y snake_case |

**Tabla de routing keys del grupo**

| Evento | Routing key | Productor |
|---|---|---|
| PlanNutricionalCreado / Actualizado / Finalizado / Cancelado | `plan_nutricional.creado` · `.actualizado` · `.finalizado` · `.cancelado` | ms-plan-nutricional |
| CalendarioEntregaCreado | `calendario.creado` | ms-catering |
| DireccionEntregaCambiada | `direccion_entrega.cambiada` | ms-catering |
| DiaSinEntregaMarcado | `dia_sin_entrega.marcado` | ms-catering |
| CalendarioEntregaCancelado / Completado | `calendario.cancelado` · `calendario.completado` | ms-catering |
| ServicioContratado | `servicio.contratado` *(a confirmar con ms-contratos-facturacion)* | ms-contratos-facturacion |
| ContratoCancelado / ContratoCompletado | `contrato.cancelado` · `contrato.completado` *(a confirmar)* | ms-contratos-facturacion |
| PacienteRegistrado | `paciente.registrado` | ms-pacientes |
| OrdenCancelada | `orden.cancelada` | ms-produccion-alimentos |

Los nombres de los eventos consumidos que figuran más abajo (`ContratoServicioRegistrado`,
`ContratoServicioCancelado`) eran la propuesta inicial; el nombre acordado es el del docx:
**`ServicioContratado`** (`tipoServicio`: `EVALUACION | ASESORAMIENTO | CATERING`) y **`ContratoCancelado`**.

---

## 2. Resumen — tabla para el documento del grupo

| Nombre del evento | Descripción | Estructura (JSON) | Productor | Consumidores |
|---|---|---|---|---|
| `CalendarioEntregaCreado` | Se generó el calendario de entregas de un paciente con catering: una entrega por día del período (HU-25). | [§3.1](#31-calendarioentregacreado) | ms-catering | ms-produccion-alimentos, ms-logistica-entrega, ms-evaluacion-seguimiento, ms-contratos-facturacion |
| `DireccionEntregaCambiada` | El paciente cambió la dirección de un día, a mano o eligiendo una dirección habitual (HU-26, HU-30). | [§3.2](#32-direccionentregacambiada) | ms-catering | ms-logistica-entrega, ms-produccion-alimentos |
| `DiaSinEntregaMarcado` | El paciente indicó que un día no recibirá su alimentación (HU-27). | [§3.3](#33-diasinentregamarcado) | ms-catering | ms-produccion-alimentos, ms-logistica-entrega |
| `EntregasDelDiaConfirmadas` | Las entregas de un día quedaron cerradas (ya no admiten cambios por la regla de 2 días): lista consolidada (HU-28, HU-29). | [§3.4](#34-entregasdeldiaconfirmadas) | ms-catering | ms-produccion-alimentos, ms-logistica-entrega |
| `CalendarioEntregaCancelado` | El calendario se canceló; sus entregas programadas quedan canceladas. | [§3.5](#35-calendarioentregacancelado) | ms-catering | ms-produccion-alimentos, ms-logistica-entrega, ms-evaluacion-seguimiento, ms-contratos-facturacion |
| `CalendarioEntregaCompletado` | El período de catering terminó. | [§3.6](#36-calendarioentregacompletado) | ms-catering | ms-evaluacion-seguimiento, ms-contratos-facturacion |
| `ContratoServicioRegistrado` | *(consumido)* Se contrató un servicio; si es catering, nace un calendario (HU-19). | [§4.1](#41-contratoservicioregistrado--de-ms-contratos-facturacion) | ms-contratos-facturacion | ms-catering, ms-plan-nutricional |
| `ContratoServicioCancelado` | *(consumido)* Se anuló un contrato vigente. | [§4.2](#42-contratoserviciocancelado--de-ms-contratos-facturacion) | ms-contratos-facturacion | ms-catering |
| `PlanNutricionalCreado` / `Finalizado` / `Cancelado` | *(consumido)* Ciclo de vida del plan del paciente. | [§4.3](#43-plannutricionalcreado--finalizado--cancelado--de-ms-plan-nutricional) | ms-plan-nutricional | ms-catering, … |
| `EtiquetaPaqueteGenerada` | *(consumido)* Cocina etiquetó el paquete de una entrega (HU-35). | [§4.4](#44-etiquetapaquetegenerada--de-ms-produccion-alimentos) | ms-produccion-alimentos | ms-catering |
| `DireccionGeolocalizada` | *(consumido)* Logística obtuvo las coordenadas de una dirección (HU-38). | [§4.5](#45-direcciongeolocalizada--de-ms-logistica-entrega) | ms-logistica-entrega | ms-catering |
| `PaqueteEntregado` | *(consumido)* El repartidor registró la constancia de entrega (HU-40). | [§4.6](#46-paqueteentregado--de-ms-logistica-entrega) | ms-logistica-entrega | ms-catering |

---

## 3. Eventos que PRODUCE ms-catering

Todos se publican **después** del `commit` del caso de uso (ver [§6](#6-cómo-se-implementaría)).

### 3.1 `CalendarioEntregaCreado`

**Cuándo:** al terminar `CrearCalendarioUseCase` (`POST /calendarios`, o al
consumir `ContratoServicioRegistrado` de tipo `CATERING`).

```json
{
  "evento_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "tipo": "CalendarioEntregaCreado",
  "version": 1,
  "ocurrido_en": "2025-12-28T09:05:00Z",
  "productor": "ms-catering",
  "correlacion_id": "0b2f8d1e-3c4a-4b5d-9e6f-7a8b9c0d1e2f",
  "datos": {
    "calendario_id": "66666666-6666-4666-8666-666666666666",
    "paciente_id": "22222222-2222-4222-8222-222222222222",
    "plan_nutricional_id": "11111111-1111-4111-8111-111111111111",
    "contrato_id": "44444444-4444-4444-8444-444444444444",
    "fecha_inicio": "2026-01-01",
    "fecha_fin": "2026-01-15",
    "total_dias": 15,
    "direccion_entrega": {
      "direccion": "Av. Banzer 123",
      "referencia": "Portón verde",
      "zona": "Equipetrol",
      "latitud": null,
      "longitud": null
    }
  }
}
```

No se envían las 15 entregas: todas nacen `PROGRAMADA` en `direccion_entrega`, una
por día entre `fecha_inicio` y `fecha_fin`. Los cambios posteriores llegan como
eventos propios.

| Consumidor | Para qué lo usa |
|---|---|
| **ms-produccion-alimentos** | Sabe qué pacientes tendrán paquete y en qué período (planificación de la producción). |
| **ms-logistica-entrega** | Registra las direcciones a geolocalizar (HU-38) para las rutas del período. |
| **ms-evaluacion-seguimiento** | **HU-12:** programa el recordatorio de evaluación quincenal "para pacientes con catering activo". |
| **ms-contratos-facturacion** | **HU-24:** mientras el paciente tiene catering activo, las evaluaciones quincenales están incluidas y no se cobra control adicional. |

### 3.2 `DireccionEntregaCambiada`

**Cuándo:** `CambiarDireccionEntregaUseCase` (`PATCH .../entregas/{fecha}/direccion`,
HU-26) o `AsignarDireccionHabitualADiaUseCase` (`PATCH .../direccion-habitual`, HU-30).
Siempre con ≥ 2 días de anticipación: lo garantiza el agregado.

```json
{
  "evento_id": "b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e",
  "tipo": "DireccionEntregaCambiada",
  "version": 1,
  "ocurrido_en": "2026-01-03T13:20:00Z",
  "productor": "ms-catering",
  "correlacion_id": "0b2f8d1e-3c4a-4b5d-9e6f-7a8b9c0d1e2f",
  "datos": {
    "calendario_id": "66666666-6666-4666-8666-666666666666",
    "entrega_id": "77777777-7777-4777-8777-777777777777",
    "paciente_id": "22222222-2222-4222-8222-222222222222",
    "fecha_entrega": "2026-01-06",
    "origen": "DIRECCION_HABITUAL",
    "nombre_direccion_habitual": "trabajo",
    "direccion_anterior": {
      "direccion": "Av. Banzer 123",
      "referencia": "Portón verde",
      "zona": "Equipetrol",
      "latitud": null,
      "longitud": null
    },
    "direccion_nueva": {
      "direccion": "Calle Libertad 456, piso 3",
      "referencia": "Oficina 3B",
      "zona": "Centro",
      "latitud": null,
      "longitud": null
    }
  }
}
```

- `origen`: `MANUAL` (HU-26) o `DIRECCION_HABITUAL` (HU-30, con `nombre_direccion_habitual`).

| Consumidor | Para qué lo usa |
|---|---|
| **ms-logistica-entrega** | Geolocaliza la nueva dirección (HU-38) y la usa en la ruta de ese día (HU-39). |
| **ms-produccion-alimentos** | La etiqueta del paquete lleva la dirección de entrega (HU-35). |

### 3.3 `DiaSinEntregaMarcado`

**Cuándo:** `MarcarDiaSinEntregaUseCase` (`PATCH .../entregas/{fecha}/sin-entrega`, HU-27).

```json
{
  "evento_id": "c3d4e5f6-a7b8-4c9d-8e0f-1a2b3c4d5e6f",
  "tipo": "DiaSinEntregaMarcado",
  "version": 1,
  "ocurrido_en": "2026-01-07T18:00:00Z",
  "productor": "ms-catering",
  "correlacion_id": "0b2f8d1e-3c4a-4b5d-9e6f-7a8b9c0d1e2f",
  "datos": {
    "calendario_id": "66666666-6666-4666-8666-666666666666",
    "entrega_id": "88888888-8888-4888-8888-888888888888",
    "paciente_id": "22222222-2222-4222-8222-222222222222",
    "fecha_entrega": "2026-01-10",
    "motivo": "Viaje de trabajo"
  }
}
```

| Consumidor | Para qué lo usa |
|---|---|
| **ms-produccion-alimentos** | No prepara el paquete de ese paciente ese día. |
| **ms-logistica-entrega** | No incluye la parada en la ruta de ese día. |

### 3.4 `EntregasDelDiaConfirmadas`

**Cuándo:** un proceso programado de ms-catering (*nuevo, a implementar*). Por la
regla de anticipación (HU-28), las entregas del día **D** solo se pueden modificar
hasta **D-2**; a partir de **D-1** quedan congeladas. Ese día se publica la lista
definitiva, justo a tiempo para la "orden de producción consolidada la tarde
anterior" (HU-32). Es el mismo consolidado que `GET /calendarios/entregas/fecha/{fecha}` (HU-29).

```json
{
  "evento_id": "d4e5f6a7-b8c9-4d0e-9f1a-2b3c4d5e6f7a",
  "tipo": "EntregasDelDiaConfirmadas",
  "version": 1,
  "ocurrido_en": "2026-01-05T00:00:00Z",
  "productor": "ms-catering",
  "correlacion_id": "9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d",
  "datos": {
    "fecha_entrega": "2026-01-06",
    "total_entregas": 1,
    "entregas": [
      {
        "entrega_id": "77777777-7777-4777-8777-777777777777",
        "calendario_id": "66666666-6666-4666-8666-666666666666",
        "paciente_id": "22222222-2222-4222-8222-222222222222",
        "plan_nutricional_id": "11111111-1111-4111-8111-111111111111",
        "direccion_entrega": {
          "direccion": "Calle Libertad 456, piso 3",
          "referencia": "Oficina 3B",
          "zona": "Centro",
          "latitud": "-17.7833000",
          "longitud": "-63.1821000"
        }
      }
    ]
  }
}
```

Solo incluye entregas `PROGRAMADA` (las `SIN_ENTREGA` y `CANCELADA` quedan fuera).

| Consumidor | Para qué lo usa |
|---|---|
| **ms-produccion-alimentos** | Cruza cada `plan_nutricional_id` con su réplica de `PlanNutricionalActualizado` y genera la **orden de producción** del día (HU-31, HU-32). |
| **ms-logistica-entrega** | Arma los lotes por repartidor y la ruta optimizada (HU-37, HU-39). |

### 3.5 `CalendarioEntregaCancelado`

**Cuándo:** `CancelarCalendarioUseCase` (`DELETE /calendarios/{id}`, o al consumir
`ContratoServicioCancelado`). Las entregas `PROGRAMADA` pasan a `CANCELADA`; las
`SIN_ENTREGA` y `ENTREGADA` se respetan.

```json
{
  "evento_id": "e5f6a7b8-c9d0-4e1f-8a2b-3c4d5e6f7a8b",
  "tipo": "CalendarioEntregaCancelado",
  "version": 1,
  "ocurrido_en": "2026-01-08T10:00:00Z",
  "productor": "ms-catering",
  "correlacion_id": "0b2f8d1e-3c4a-4b5d-9e6f-7a8b9c0d1e2f",
  "datos": {
    "calendario_id": "66666666-6666-4666-8666-666666666666",
    "paciente_id": "22222222-2222-4222-8222-222222222222",
    "fechas_canceladas": ["2026-01-09", "2026-01-11", "2026-01-12", "2026-01-13", "2026-01-14", "2026-01-15"]
  }
}
```

| Consumidor | Para qué lo usa |
|---|---|
| **ms-produccion-alimentos** | Deja de producir para el paciente en `fechas_canceladas`. |
| **ms-logistica-entrega** | Quita esas paradas de las rutas. |
| **ms-evaluacion-seguimiento** | Desactiva el recordatorio quincenal (HU-12). |
| **ms-contratos-facturacion** | El paciente deja de tener catering activo: desde ahora sus controles se cobran (HU-22, HU-24). |

### 3.6 `CalendarioEntregaCompletado`

**Cuándo:** al pasar `fecha_fin` (`CalendarioEntrega.completar_calendario()` ya
existe en el dominio; falta el proceso programado que lo invoque).

```json
{
  "evento_id": "f6a7b8c9-d0e1-4f2a-9b3c-4d5e6f7a8b9c",
  "tipo": "CalendarioEntregaCompletado",
  "version": 1,
  "ocurrido_en": "2026-01-16T00:00:00Z",
  "productor": "ms-catering",
  "correlacion_id": "0b2f8d1e-3c4a-4b5d-9e6f-7a8b9c0d1e2f",
  "datos": {
    "calendario_id": "66666666-6666-4666-8666-666666666666",
    "paciente_id": "22222222-2222-4222-8222-222222222222",
    "fecha_fin": "2026-01-15",
    "entregas_realizadas": 13,
    "dias_sin_entrega": 1
  }
}
```

| Consumidor | Para qué lo usa |
|---|---|
| **ms-evaluacion-seguimiento** | Cierra el ciclo de recordatorios quincenales (HU-12). |
| **ms-contratos-facturacion** | El paciente deja de tener catering activo (HU-24). |

---

## 4. Eventos que CONSUME ms-catering (lo que pido a los demás)

Son **propuestas**: el equipo productor decide el contrato final.

### 4.1 `ContratoServicioRegistrado` — de ms-contratos-facturacion

**Pedido a:** Joel Cesar Barco Pañuni (BC4). **HU:** HU-19 ("Plan de Catering 15/30 días").

```json
{
  "evento_id": "a7b8c9d0-e1f2-4a3b-8c4d-5e6f7a8b9c0d",
  "tipo": "ContratoServicioRegistrado",
  "version": 1,
  "ocurrido_en": "2025-12-28T09:00:00Z",
  "productor": "ms-contratos-facturacion",
  "correlacion_id": "0b2f8d1e-3c4a-4b5d-9e6f-7a8b9c0d1e2f",
  "datos": {
    "contrato_id": "44444444-4444-4444-8444-444444444444",
    "paciente_id": "22222222-2222-4222-8222-222222222222",
    "tipo_servicio": "CATERING",
    "duracion_dias": 15,
    "fecha_inicio": "2026-01-01",
    "fecha_fin": "2026-01-15",
    "direccion_entrega": {
      "direccion": "Av. Banzer 123",
      "referencia": "Portón verde",
      "zona": "Equipetrol"
    }
  }
}
```

**Qué haría BC5:** si `tipo_servicio = CATERING`, ejecutar `CrearCalendarioUseCase`
con esas fechas y `direccion_entrega` como dirección inicial (hoy se crea a mano con
`POST /calendarios`). Los demás tipos se ignoran.
**Imprescindible:** `direccion_entrega` — sin ella no se puede crear el calendario.
Si BC4 no la tiene, la alternativa es pedirla a ms-pacientes por REST.

### 4.2 `ContratoServicioCancelado` — de ms-contratos-facturacion

**Pedido a:** Joel Cesar Barco Pañuni (BC4).

```json
{
  "evento_id": "b8c9d0e1-f2a3-4b4c-9d5e-6f7a8b9c0d1e",
  "tipo": "ContratoServicioCancelado",
  "version": 1,
  "ocurrido_en": "2026-01-08T09:55:00Z",
  "productor": "ms-contratos-facturacion",
  "correlacion_id": "0b2f8d1e-3c4a-4b5d-9e6f-7a8b9c0d1e2f",
  "datos": {
    "contrato_id": "44444444-4444-4444-8444-444444444444",
    "paciente_id": "22222222-2222-4222-8222-222222222222",
    "tipo_servicio": "CATERING",
    "motivo": "Solicitud del paciente"
  }
}
```

**Qué haría BC5:** `CancelarCalendarioUseCase` sobre el calendario activo del
paciente, que a su vez publica `CalendarioEntregaCancelado`.

### 4.3 `PlanNutricionalCreado` / `Finalizado` / `Cancelado` — de ms-plan-nutricional

**Propio** (BC3). Contrato completo en `Repo-ms-plan-nutricional/EVENTOS_INTEGRACION.md` §3.
Campos que BC5 usa:

```json
{
  "tipo": "PlanNutricionalCreado",
  "datos": {
    "plan_id": "11111111-1111-4111-8111-111111111111",
    "paciente_id": "22222222-2222-4222-8222-222222222222",
    "fecha_inicio": "2026-01-01",
    "fecha_fin": "2026-01-15"
  }
}
```

**Qué haría BC5:** con `Creado`, asignar `plan_nutricional_id` al calendario activo
del paciente y a sus entregas futuras; con `Finalizado` o `Cancelado`, desvincularlo
de las entregas futuras. El calendario **no** se cancela por el plan: lo rige el contrato.
*Requiere un método nuevo en el agregado* (`vincular_plan_nutricional`); hoy el plan
solo se fija al crear el calendario.

### 4.4 `EtiquetaPaqueteGenerada` — de ms-produccion-alimentos

**Pedido a:** Katering Cristal Flores Hilari (BC6). **HU:** HU-35.

```json
{
  "evento_id": "c9d0e1f2-a3b4-4c5d-8e6f-7a8b9c0d1e2f",
  "tipo": "EtiquetaPaqueteGenerada",
  "version": 1,
  "ocurrido_en": "2026-01-05T20:30:00Z",
  "productor": "ms-produccion-alimentos",
  "correlacion_id": "9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d",
  "datos": {
    "entrega_id": "77777777-7777-4777-8777-777777777777",
    "paciente_id": "22222222-2222-4222-8222-222222222222",
    "fecha_entrega": "2026-01-06",
    "nombre_paciente": "María Pérez",
    "codigo_paciente": "PAC-0001",
    "numero_identificacion": "1234567",
    "direccion_entrega": "Calle Libertad 456, piso 3"
  }
}
```

Los campos son exactamente los del VO `Etiqueta` de BC5.
**Qué haría BC5:** asignar la etiqueta a la `Entrega` (`tiene_etiqueta = true` en
la API). *Antes hay que corregir el hallazgo 6 de `tests/README.md` §8.2: hoy la
etiqueta se guarda pero no se relee de la base.*

### 4.5 `DireccionGeolocalizada` — de ms-logistica-entrega

**Pedido a:** Elvis Encinas (BC7). **HU:** HU-38.

```json
{
  "evento_id": "d0e1f2a3-b4c5-4d6e-9f7a-8b9c0d1e2f3a",
  "tipo": "DireccionGeolocalizada",
  "version": 1,
  "ocurrido_en": "2026-01-03T13:21:00Z",
  "productor": "ms-logistica-entrega",
  "correlacion_id": "0b2f8d1e-3c4a-4b5d-9e6f-7a8b9c0d1e2f",
  "datos": {
    "entrega_id": "77777777-7777-4777-8777-777777777777",
    "direccion": "Calle Libertad 456, piso 3",
    "latitud": "-17.7833000",
    "longitud": "-63.1821000"
  }
}
```

**Qué haría BC5:** completar `latitud`/`longitud` de la `DireccionEntrega` de esa
entrega (los campos ya existen en el VO y en la tabla `entregas`).

### 4.6 `PaqueteEntregado` — de ms-logistica-entrega

**Pedido a:** Elvis Encinas (BC7). **HU:** HU-40.

```json
{
  "evento_id": "e1f2a3b4-c5d6-4e7f-8a9b-0c1d2e3f4a5b",
  "tipo": "PaqueteEntregado",
  "version": 1,
  "ocurrido_en": "2026-01-06T12:45:00Z",
  "productor": "ms-logistica-entrega",
  "correlacion_id": "9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d",
  "datos": {
    "entrega_id": "77777777-7777-4777-8777-777777777777",
    "paciente_id": "22222222-2222-4222-8222-222222222222",
    "fecha_entrega": "2026-01-06",
    "entregado_en": "2026-01-06T12:44:10Z",
    "tipo_constancia": "FIRMA"
  }
}
```

**Qué haría BC5:** `Entrega.registrar_entrega()` → estado `ENTREGADA` (el estado y
el método ya existen; falta el caso de uso que los invoque). Así el paciente ve en
su calendario (HU-25) qué días ya recibió.

---

## 5. Eventos de dominio que NO se publican

| Evento de dominio | Por qué no es de integración |
|---|---|
| `DireccionHabitualRegistrada` | Es una libreta de direcciones del paciente dentro de BC5. Solo importa cuando se **usa** en un día, y eso ya sale como `DireccionEntregaCambiada` con `origen = DIRECCION_HABITUAL`. |
| Rechazo por anticipación insuficiente (HU-28) | Es una regla que **impide** un cambio: no pasó nada que otros deban saber. El cierre del día sí se publica (`EntregasDelDiaConfirmadas`). |

---

## 6. Cómo está implementado

1. **Transactional Outbox:** `CalendarioEntrega` anota eventos de dominio
   (`domain/model/eventos.py`); `CalendarioEntregaRepositoryImpl.guardar()` inserta la fila en
   `outbox` **en la misma sesión** que el calendario. Migración Alembic `7c1e2a9b4d10`.
2. **Relay** (`infrastructure/messaging/outbox_relay.py`) con `FOR UPDATE SKIP LOCKED`: con 3
   réplicas, cada evento lo publica una sola.
3. **Consumidor idempotente** (cola `ms-catering.eventos`, inbox `eventos_procesados`):
   - `servicio.contratado` (CATERING) → crea el calendario (dirección provisional «Por definir»);
     si el paciente ya tiene uno activo, no crea otro (cubre el hallazgo 3 de `tests/README.md` §8.2).
   - `plan_nutricional.creado` → vincula el plan al calendario activo.
   - `plan_nutricional.cancelado` / `contrato.cancelado` → cancela el calendario (publica `calendario.cancelado`).
   - `plan_nutricional.finalizado` / `contrato.completado` → completa el calendario (publica `calendario.completado`).
4. **Pendiente:** el proceso programado de `EntregasDelDiaConfirmadas` (diario, inicio de D-1) y el
   consumo de `IncidenciaEntregaRegistrada` (día de reposición).

## 7. Integraciones síncronas que ya existen (REST, con contrato Pact)

| Relación | Tipo | Estado |
|---|---|---|
| `app-paciente` → `GET /calendarios/{id}`, `GET /calendarios/paciente/{id}` | Consulta (HU-25) | ✅ verificado (`pacts/app-paciente-ms-catering.json`) |
| ms-catering → `GET /pacientes/{id}` de ms-pacientes | Consulta (datos de la etiqueta) | ⏳ pact generado, lo verifica ms-pacientes |
| Paciente → `PATCH .../direccion`, `.../sin-entrega`, `.../direccion-habitual` | Comandos desde la app (HU-26, HU-27, HU-30) | ✅ cubiertos por integración y Postman |

## 8. Pendientes por equipo

| Equipo | Qué necesito acordar |
|---|---|
| ms-contratos-facturacion (BC4) | Publicar `ContratoServicioRegistrado` (con `direccion_entrega` para catering) y `ContratoServicioCancelado`. Consumir `CalendarioEntregaCreado` / `Cancelado` / `Completado` para HU-24. |
| ms-evaluacion-seguimiento (BC2) | Consumir `CalendarioEntregaCreado` / `Cancelado` / `Completado` para el recordatorio quincenal (HU-12). |
| ms-produccion-alimentos (BC6) | Consumir `EntregasDelDiaConfirmadas`, `DiaSinEntregaMarcado`, `DireccionEntregaCambiada`. Publicar `EtiquetaPaqueteGenerada`. |
| ms-logistica-entrega (BC7) | Consumir `EntregasDelDiaConfirmadas`, `DireccionEntregaCambiada`, `DiaSinEntregaMarcado`, `CalendarioEntregaCancelado`. Publicar `DireccionGeolocalizada` y `PaqueteEntregado`. |
| ms-plan-nutricional (BC3, propio) | Publicar `PlanNutricionalCreado` / `Finalizado` / `Cancelado` (ver su `EVENTOS_INTEGRACION.md`). |
