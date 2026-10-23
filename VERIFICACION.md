# Verificación del stack — ms-catering

Evidencia de ejecución del `docker-compose.yml` de este microservicio. Todas las salidas de esta
guía son reales, capturadas al levantar el stack.

**Entorno:** Docker Desktop · Windows 10 · imagen
[`betonavarro/ms-catering:0.1.0`](https://hub.docker.com/r/betonavarro/ms-catering)

Para reproducir todo lo que sigue basta con el archivo `docker-compose.yml` en una carpeta vacía:
la imagen de la API se descarga de Docker Hub, y la red y el volumen los crea Compose.

---

## 0. Construcción y publicación de la imagen

```bash
docker build -t betonavarro/ms-catering:0.1.0 .
docker login
docker push betonavarro/ms-catering:0.1.0
```

Comprobación de que Alembic quedó dentro de la imagen (lo necesita `catering_migrate`) y de que la
app importa correctamente:

```
$ docker run --rm betonavarro/ms-catering:0.1.0 uv run alembic --version
alembic 1.18.5

$ docker run --rm betonavarro/ms-catering:0.1.0 \
    uv run python -c "from catering.presentation.api.main import app; print(app.title)"
ms-catering — NUR-TRICENTER

$ docker images betonavarro/ms-catering:0.1.0 --format "{{.Repository}}:{{.Tag}} {{.Size}}"
betonavarro/ms-catering:0.1.0 398MB
```

> El `Dockerfile` **no** usa `--no-dev` a propósito: `alembic` está declarado en
> `[dependency-groups] dev` de `pyproject.toml`. Con `--no-dev`, el servicio de migraciones
> fallaría con "command not found".

---

## 1. Los tres servicios

| Servicio | Rol | Imagen | Puerto en el host |
|---|---|---|---|
| `catering_api` | API (FastAPI) | `betonavarro/ms-catering:0.1.0` | 8020-8022 |
| `catering_db` | Base de datos | `postgres:15` | 5433 |
| `catering_cache` | Caché | `redis:7-alpine` | 6381 |

Existe un cuarto contenedor, `catering_migrate`, que no es un servicio de larga vida: ejecuta las
migraciones de Alembic una sola vez y termina. Se incluyó para poder demostrar la condición
`service_completed_successfully`.

---

## 2. Arranque del stack y `depends_on` con condición

```bash
docker compose up -d
```

La propia traza de arranque demuestra que las condiciones se respetan. Compose no arranca nada en
paralelo a ciegas: espera.

```
 Volume catering_postgres_data Created
 Container ms-catering-catering_cache-1 Started
 Container ms-catering-catering_db-1 Started
 Container ms-catering-catering_db-1 Waiting
 Container ms-catering-catering_db-1 Healthy          <- espera a que la BD este sana
 Container ms-catering-catering_migrate-1 Started     <- recien ahi migra
 Container ms-catering-catering_cache-1 Waiting
 Container ms-catering-catering_migrate-1 Waiting
 Container ms-catering-catering_cache-1 Healthy
 Container ms-catering-catering_migrate-1 Exited      <- migracion termino con exito
 Container ms-catering-catering_api-1 Started         <- recien ahi arranca la API
```

Las tres condiciones usadas, y qué garantiza cada una:

| Condición | Dónde | Qué garantiza |
|---|---|---|
| `service_healthy` | api → db | La API no arranca hasta que Postgres acepta conexiones. |
| `service_healthy` | api → cache | La API no arranca hasta que Redis responde `PONG`. |
| `service_completed_successfully` | api → migrate | La API no arranca hasta que el esquema está migrado. |

Sin estas condiciones, la API arrancaría contra una base de datos que todavía no acepta conexiones,
o contra un esquema inexistente, y fallaría en el primer request.

**Verificación de que la migración corrió una sola vez y terminó bien:**

```
$ docker compose ps -a --format '{{.Service}} | {{.Status}}' | grep migrate
catering_migrate | Exited (0) 31 seconds ago

$ docker compose exec catering_db psql -U postgres -d db_catering \
    -c "select version_num from alembic_version;"
 version_num
--------------
 126a03743ded
(1 row)
```

`Exited (0)` es el código de salida cero que exige `service_completed_successfully`. Si Alembic
hubiera fallado, el contenedor saldría con código distinto de cero y la API nunca arrancaría — que
es exactamente el comportamiento deseado.

**Idempotencia:** un segundo `docker compose up -d` vuelve a ejecutar `catering_migrate`, que sale
en 0 sin recrear tablas (Alembic ve que ya está en `head`).

---

## 3. Healthchecks

Cada servicio define su propia sonda, apropiada a su tecnología:

| Servicio | Sonda | Intervalo |
|---|---|---|
| `catering_db` | `pg_isready -U postgres -d db_catering` | 5s, 5 reintentos |
| `catering_cache` | `redis-cli ping` | 5s, 5 reintentos |
| `catering_api` | `curl -f http://localhost:8000/docs` | 10s, 5 reintentos, `start_period` 20s |

El `start_period` de 20s en la API existe porque el arranque de Uvicorn más la conexión inicial a la
base de datos tarda unos segundos; sin él, los primeros fallos contarían como reintentos y el
contenedor sería marcado `unhealthy` antes de estar realmente listo.

> Nota: el healthcheck de la API usa `curl`, que no viene en `python:3.12-slim`. Por eso el
> `Dockerfile` lo instala explícitamente (`apt-get install -y --no-install-recommends curl`). Es un
> detalle fácil de pasar por alto: sin esa línea el healthcheck falla siempre.
>
> La API no expone un endpoint `/health` propio; se usa `/docs`, que FastAPI publica de serie.

**Estado observado:**

```
$ docker compose ps -a --format '{{.Service}} | {{.Status}} | {{.Ports}}'
catering_api      | Up 31 seconds (healthy) | 0.0.0.0:8020->8000/tcp
catering_cache    | Up 40 seconds (healthy) | 0.0.0.0:6381->6379/tcp
catering_db       | Up 40 seconds (healthy) | 0.0.0.0:5433->5432/tcp
catering_migrate  | Exited (0) 31 seconds ago |
```

Los tres servicios de larga vida en `healthy`. La API responde:

```
$ curl -o /dev/null -w "%{http_code}" http://localhost:8020/docs
200

$ curl -w "\n%{http_code}\n" http://localhost:8020/calendarios
[]
200
```

La lista vacía con `200` prueba que la API llegó a Postgres y consultó una tabla que existe — es
decir, que las migraciones corrieron contra la base correcta.

---

## 4. Red

El stack define una red bridge propia, `nurtricenter_net`, con nombre fijo — **la misma que usa
`ms-plan-nutricional`** — para poder integrarse al `docker-compose.yml` grupal del proyecto.

```
$ docker network inspect nurtricenter_net --format '{{range .Containers}}{{.Name}} -> {{.IPv4Address}}{{println}}{{end}}'
ms-catering-catering_db-1    -> 172.21.0.3/16
ms-catering-catering_cache-1 -> 172.21.0.2/16
ms-catering-catering_api-1   -> 172.21.0.4/16
```

Los contenedores comparten la subred `172.21.0.0/16`, que es lo que les permite verse entre sí sin
exponer nada al host.

### La red aísla de verdad

Un contenedor que **no** pertenece a `nurtricenter_net` no puede ni siquiera resolver el nombre de
la base de datos:

```
$ docker run --rm redis:7-alpine nslookup catering_db
** server can't find catering_db: NXDOMAIN
```

El mismo contenedor, conectado a la red, sí:

```
$ docker run --rm --network nurtricenter_net redis:7-alpine nslookup catering_db
Name:	catering_db
Address: 172.21.0.3
```

Esto confirma que la red no es decorativa: define un límite real de visibilidad.

### Comunicación entre microservicios

Con ambos stacks arriba, `ms-catering` alcanza a `ms-plan-nutricional` por nombre de servicio, sin
pasar por el host:

```
$ docker compose exec catering_api curl -o /dev/null -w "%{http_code}\n" \
    http://plan_nutricional_api:8000/docs
200
```

Es la prueba de que compartir `nurtricenter_net` integra de verdad los dos Bounded Contexts: cuando
el gateway hacia otro BC deje de ser un mock, esta es la ruta que usará.

---

## 5. DNS interno

Docker levanta un servidor DNS embebido en `127.0.0.11` dentro de cada red definida por el usuario.
Ese DNS resuelve **el nombre del servicio** tal como aparece en el compose, y es la razón por la que
las cadenas de conexión pueden escribirse así:

```yaml
DATABASE_URL: postgresql+asyncpg://postgres:password@catering_db:5432/db_catering
REDIS_URL:    redis://catering_cache:6379/0
```

No hay IPs escritas a mano en ningún lado. Las IPs cambian en cada arranque; los nombres no. Nótese
también que dentro de la red se usa el puerto **5432** (el del contenedor), no el 5433 que se publica
al host: el mapeo de puertos solo aplica desde fuera.

**Resolución desde el contenedor de la API:**

```
$ docker compose exec catering_api getent hosts catering_db
172.21.0.3      catering_db

$ docker compose exec catering_api getent hosts catering_cache
172.21.0.2      catering_cache
```

Ambos nombres resuelven a las mismas IPs que reportó `docker network inspect`, lo que cierra el
círculo entre red y DNS.

---

## 6. Escalado

Cubierto en detalle en [`ESCALADO.md`](ESCALADO.md). En resumen, con `ports: "8020-8022:8000"`:

```
$ docker compose up -d --scale catering_api=3
$ docker compose ps
ms-catering-catering_api-1 | Up About a minute (healthy) | 0.0.0.0:8020->8000/tcp
ms-catering-catering_api-2 | Up 30 seconds (healthy)     | 0.0.0.0:8022->8000/tcp
ms-catering-catering_api-3 | Up 30 seconds (healthy)     | 0.0.0.0:8021->8000/tcp

$ for p in 8020 8021 8022; do curl -o /dev/null -w "$p -> %{http_code}\n" http://localhost:$p/docs; done
8020 -> 200
8021 -> 200
8022 -> 200
```

Las tres réplicas comparten estado — un calendario creado contra 8020 se lee desde 8021 y 8022 — y
el DNS interno devuelve tres registros A para `catering_api`, repartiendo el tráfico entre ellas.

---

## 7. Conclusiones

1. **Los healthchecks y `depends_on` con condición resuelven un problema real de orden de
   arranque.** Sin ellos la API arrancaría antes que la base de datos y fallaría en el primer
   request. `service_completed_successfully` extiende la idea a tareas de un solo uso como las
   migraciones.

2. **La red definida por el usuario es la que habilita el DNS por nombre de servicio.** En la red
   `bridge` por defecto ese DNS no existe, y habría que enlazar contenedores o codificar IPs. Usar
   la misma red que `ms-plan-nutricional` es lo que permite que ambos BC se comuniquen.

3. **Escalar horizontalmente solo funciona en servicios sin estado.** La API se replica sin problema
   porque delega todo su estado a Postgres. La base de datos y el caché **no** pueden replicarse con
   `--scale`: cada réplica levantaría su propio almacenamiento y los datos divergirían.

4. **Publicar puertos al host limita el escalado.** El rango `8020-8022` funciona pero fija un techo
   de tres réplicas. En un despliegue real se pondría un balanceador o un ingress delante.

---

## Apéndice — Comandos para reproducir

```bash
# Construir y publicar
docker build -t betonavarro/ms-catering:0.1.0 .
docker login && docker push betonavarro/ms-catering:0.1.0

# Levantar
docker compose up -d

# Healthchecks
docker compose ps
docker inspect --format "{{.State.Health.Status}}" <contenedor>

# Red
docker network inspect nurtricenter_net

# DNS
docker compose exec catering_api getent hosts catering_db
docker compose exec catering_api getent hosts catering_cache

# Escalado
docker compose up -d --scale catering_api=3
docker compose exec catering_cache nslookup catering_api

# Limpiar
docker compose down -v
```
