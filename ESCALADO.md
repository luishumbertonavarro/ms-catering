# Prueba de escalado — ms-catering

## Cómo estaba

El microservicio no tenía imagen propia: el compose solo levantaba la base de datos y la API se
corría a mano en la máquina, siempre sobre el puerto 8000. Con una sola copia de la aplicación
funcionaba, pero esa configuración asumía que nunca habría más de una, y además dependía de que
cada persona levantara la API por su cuenta.

## Qué pasaba

Al empaquetar la API en un contenedor y pedirle a Docker que levantara tres copias al mismo tiempo
con un puerto fijo, el comando fallaba de inmediato con un error de "puerto ya ocupado". La primera
copia tomaba el puerto y las otras dos se quedaban sin lugar donde publicarse, así que ni siquiera
llegaban a arrancar. El resultado era que seguía habiendo una sola copia corriendo, igual que antes.

La causa es que un puerto del host solo puede estar ocupado por un proceso: `ports:` crea un mapeo
uno a uno host→contenedor, así que es intrínsecamente incompatible con N réplicas.

## Qué se hizo

Se creó una imagen propia del servicio (`betonavarro/ms-catering:0.1.0`, publicada en Docker Hub) y
se cambió la configuración para que la API pudiera usar un rango de puertos en lugar de uno solo:

```yaml
ports:
  - "8020-8022:8000"
```

Así cada copia recibe un puerto libre y las tres pueden convivir. El rango se eligió fuera del 8000
y separado del de `ms-plan-nutricional` (8010-8012) para no chocar con los microservicios de los
demás integrantes del grupo cuando este archivo se incluye en el `docker-compose.yml` grupal.

También se quitó el `container_name: catering_db` que traía el compose anterior: un nombre de
contenedor fijo es único por definición y bloquea cualquier intento de replicar ese servicio.

## Qué se observó

Las tres copias arrancaron correctamente y respondieron sin problemas, cada una desde su propio
puerto:

```
$ docker compose up -d --scale catering_api=3
 Container ms-catering-catering_api-3 Started
 Container ms-catering-catering_api-2 Started

$ docker compose ps
ms-catering-catering_api-1   | Up About a minute (healthy) | 0.0.0.0:8020->8000/tcp
ms-catering-catering_api-2   | Up 30 seconds (healthy)     | 0.0.0.0:8022->8000/tcp
ms-catering-catering_api-3   | Up 30 seconds (healthy)     | 0.0.0.0:8021->8000/tcp
ms-catering-catering_cache-1 | Up About a minute (healthy) | 0.0.0.0:6381->6379/tcp
ms-catering-catering_db-1    | Up About a minute (healthy) | 0.0.0.0:5433->5432/tcp

$ for p in 8020 8021 8022; do curl -o /dev/null -w "$p -> %{http_code}\n" http://localhost:$p/docs; done
8020 -> 200
8021 -> 200
8022 -> 200
```

Nótese que la asignación de puertos no sigue el orden del sufijo (`api-2` recibió el 8022 y `api-3`
el 8021): Compose reparte los puertos libres del rango sin garantizar correspondencia con el número
de réplica.

Se comprobó que las tres comparten la misma base de datos: se creó un calendario desde la primera
copia y las otras dos lo mostraron de inmediato.

```
$ curl -X POST http://localhost:8020/calendarios -H "Content-Type: application/json" -d '{...}'
{"id":"db998d2d-ef96-4392-8dd9-9a3a928e22a1","total_dias":15,"estado":"ACTIVO",...}

$ curl -o /dev/null -w "%{http_code}" http://localhost:8021/calendarios/db998d2d-ef96-4392-8dd9-9a3a928e22a1
200
$ curl -o /dev/null -w "%{http_code}" http://localhost:8022/calendarios/db998d2d-ef96-4392-8dd9-9a3a928e22a1
200
```

Esto confirma que la aplicación no guarda información propia en memoria: todo el estado vive en
Postgres, que es compartido. Es justamente lo que permite tener varias copias trabajando en paralelo
sin que se contradigan entre sí.

También se verificó que Docker reconoce automáticamente a las tres copias bajo un mismo nombre
interno y reparte las solicitudes entre ellas:

```
$ docker compose exec catering_cache nslookup catering_api
Server:		127.0.0.11
Address:	127.0.0.11:53

Name:	catering_api
Address: 172.21.0.4
Name:	catering_api
Address: 172.21.0.6
Name:	catering_api
Address: 172.21.0.5
```

Tres registros A para un mismo nombre, devueltos en orden rotativo. Es un balanceo rudimentario
—por DNS, sin health-awareness ni control de carga real— pero suficiente para repartir tráfico entre
réplicas equivalentes.

> Detalle práctico: `getent hosts` devuelve **solo la primera** dirección, así que no sirve para
> evidenciar esto. Hay que usar `nslookup` (o `getent ahostsv4`) para ver los tres registros.

Y la preparación de la base de datos se ejecuta una sola vez, no una por cada copia:

```
$ docker compose ps -a --format '{{.Service}} | {{.Status}}' | grep migrate
catering_migrate | Exited (0) 39 seconds ago
```

## Conclusión

Multiplicar copias solo funciona bien en servicios que no guardan información propia, como la API.
La base de datos y el caché no se pueden multiplicar de esta forma, porque cada uno maneja
información que no se compartiría correctamente entre copias; para ellos existen mecanismos
distintos y específicos (replicación primario/réplica en Postgres, Redis Cluster).

El rango `8020-8022` resuelve el problema pero fija un techo de tres réplicas. En un despliegue real
no se publicarían puertos por réplica: se pondría un balanceador o un ingress delante y las réplicas
quedarían accesibles solo por la red interna.
