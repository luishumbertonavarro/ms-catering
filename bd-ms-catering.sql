-- =============================================================================
-- SCRIPT DE BASE DE DATOS: ms-catering (BC5 – Gestión de Catering)
-- Sistema: NUR-TRICENTER – Sistema Integral de Gestión Nutricional
-- Base de datos: db_catering
--
-- Este script se ejecuta AUTOMÁTICAMENTE al primer arranque del contenedor
-- catering_db (está montado en /docker-entrypoint-initdb.d/).
--
-- Si necesitas ejecutarlo manualmente (por ejemplo, tras borrar y recrear
-- el contenedor sin borrar el volumen):
--   docker exec -i catering_db psql -U postgres -d db_catering < bd-ms-catering.sql
--
-- El script es idempotente: usa CREATE TABLE IF NOT EXISTS y CREATE INDEX IF NOT EXISTS.
-- =============================================================================

-- Extensión necesaria para gen_random_uuid() como valor por defecto de PKs
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =============================================================================
-- TABLA: calendarios_entrega  (Aggregate Root: CalendarioEntrega)
-- =============================================================================
CREATE TABLE IF NOT EXISTS calendarios_entrega (
    id                  UUID            NOT NULL DEFAULT gen_random_uuid(),
    paciente_id         UUID            NOT NULL,
    fecha_inicio        DATE            NOT NULL,
    fecha_fin           DATE            NOT NULL,
    estado              VARCHAR(20)     NOT NULL,   -- ACTIVO | PAUSADO | COMPLETADO | CANCELADO
    plan_nutricional_id UUID            NULL,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT now(),

    CONSTRAINT pk_calendarios_entrega PRIMARY KEY (id),
    CONSTRAINT ck_calendarios_estado CHECK (estado IN ('ACTIVO', 'PAUSADO', 'COMPLETADO', 'CANCELADO')),
    CONSTRAINT ck_calendarios_fechas CHECK (fecha_fin >= fecha_inicio)
);

CREATE INDEX IF NOT EXISTS idx_calendarios_paciente_id
    ON calendarios_entrega (paciente_id);

CREATE INDEX IF NOT EXISTS idx_calendarios_estado
    ON calendarios_entrega (estado);

-- =============================================================================
-- TABLA: entregas  (Entidad dentro del agregado CalendarioEntrega)
-- Incluye los campos de DireccionEntrega (Value Object aplanado) y
-- los campos de Etiqueta (Value Object aplanado, nullable hasta generarse).
-- =============================================================================
CREATE TABLE IF NOT EXISTS entregas (
    id                          UUID            NOT NULL DEFAULT gen_random_uuid(),
    calendario_id               UUID            NOT NULL,
    fecha                       DATE            NOT NULL,
    estado                      VARCHAR(20)     NOT NULL,   -- PROGRAMADA | SIN_ENTREGA | CANCELADA | ENTREGADA
    -- DireccionEntrega (Value Object aplanado)
    direccion                   VARCHAR(500)    NOT NULL,
    referencia                  VARCHAR(500)    NULL,
    zona                        VARCHAR(100)    NULL,
    latitud                     NUMERIC(10, 7)  NULL,
    longitud                    NUMERIC(10, 7)  NULL,
    -- Referencia al plan nutricional (contexto externo)
    plan_nutricional_id         UUID            NULL,
    -- Etiqueta (Value Object aplanado, se completa al generar la etiqueta de entrega)
    etiqueta_nombre_paciente    VARCHAR(200)    NULL,
    etiqueta_codigo_paciente    VARCHAR(50)     NULL,
    etiqueta_numero_id          VARCHAR(50)     NULL,

    CONSTRAINT pk_entregas PRIMARY KEY (id),
    CONSTRAINT fk_entregas_calendario
        FOREIGN KEY (calendario_id) REFERENCES calendarios_entrega (id) ON DELETE CASCADE,
    CONSTRAINT ck_entregas_estado CHECK (estado IN ('PROGRAMADA', 'SIN_ENTREGA', 'CANCELADA', 'ENTREGADA'))
);

CREATE INDEX IF NOT EXISTS idx_entregas_calendario_id
    ON entregas (calendario_id);

CREATE INDEX IF NOT EXISTS idx_entregas_fecha
    ON entregas (fecha);

CREATE INDEX IF NOT EXISTS idx_entregas_calendario_fecha
    ON entregas (calendario_id, fecha);

-- =============================================================================
-- TABLA: direcciones_habituales  (Entidad dentro del agregado)
-- Direcciones frecuentes del paciente registradas en su calendario.
-- =============================================================================
CREATE TABLE IF NOT EXISTS direcciones_habituales (
    id              UUID            NOT NULL DEFAULT gen_random_uuid(),
    calendario_id   UUID            NOT NULL,
    paciente_id     UUID            NOT NULL,
    nombre          VARCHAR(100)    NOT NULL,
    -- DireccionEntrega (Value Object aplanado)
    direccion       VARCHAR(500)    NOT NULL,
    referencia      VARCHAR(500)    NULL,
    zona            VARCHAR(100)    NULL,
    latitud         NUMERIC(10, 7)  NULL,
    longitud        NUMERIC(10, 7)  NULL,
    es_principal    BOOLEAN         NOT NULL DEFAULT FALSE,

    CONSTRAINT pk_direcciones_habituales PRIMARY KEY (id),
    CONSTRAINT fk_direcciones_calendario
        FOREIGN KEY (calendario_id) REFERENCES calendarios_entrega (id) ON DELETE CASCADE,
    CONSTRAINT uq_direcciones_calendario_nombre
        UNIQUE (calendario_id, nombre)   -- refleja DireccionHabitualDuplicadaError en dominio
);

CREATE INDEX IF NOT EXISTS idx_direcciones_calendario_id
    ON direcciones_habituales (calendario_id);

-- =============================================================================
-- TABLA: dias_sin_entrega  (Value Object DiaSinEntrega persistido como tabla)
-- Registra los días en que el paciente no desea recibir su alimentación.
-- =============================================================================
CREATE TABLE IF NOT EXISTS dias_sin_entrega (
    id              UUID            NOT NULL DEFAULT gen_random_uuid(),
    calendario_id   UUID            NOT NULL,
    fecha           DATE            NOT NULL,
    motivo          VARCHAR(500)    NULL,

    CONSTRAINT pk_dias_sin_entrega PRIMARY KEY (id),
    CONSTRAINT fk_dias_calendario
        FOREIGN KEY (calendario_id) REFERENCES calendarios_entrega (id) ON DELETE CASCADE,
    CONSTRAINT uq_dias_sin_entrega_fecha
        UNIQUE (calendario_id, fecha)   -- un solo registro por día por calendario
);

CREATE INDEX IF NOT EXISTS idx_dias_sin_entrega_calendario_id
    ON dias_sin_entrega (calendario_id);

-- =============================================================================
-- FIN DEL SCRIPT
-- =============================================================================
