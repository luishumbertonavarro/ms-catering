FROM python:3.12-slim

# despeus de actualizar se realiza una limpieza de cache para reducir el tamaño de la imagen final
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# uv: gestor de dependencias/entorno del proyecto
COPY --from=ghcr.io/astral-sh/uv:0.12.7 /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
# Capa cacheada: solo dependencias. No se invalida al editar el codigo.
# Sin --no-dev a proposito: alembic vive en [dependency-groups] dev y el
# servicio de migraciones lo necesita dentro de la imagen. El grupo `test`
# (pytest, pact-python) si se excluye: no hace falta en runtime.
RUN uv sync --frozen --no-install-project --no-group test

# Codigo y archivos necesarios para correr la app y las migraciones
COPY src/ ./src/
COPY main.py alembic.ini ./
COPY migrations/ ./migrations/

# Instala el proyecto en si (rapido: las dependencias ya estan)
RUN uv sync --frozen --no-group test

EXPOSE 8000

# Arranque de la API escuchando en todas las interfaces del contenedor (0.0.0.0)
CMD ["uv", "run", "uvicorn", "catering.presentation.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
