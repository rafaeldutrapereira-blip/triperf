-- ============================================================
-- KonaLabs — Training Sync Module  /  PostgreSQL Schema
-- Módulo de Planificación y Sincronización con Garmin API
-- ============================================================

-- ──────────────────────────────────────────────────────────
-- EXTENSION: UUID generation
-- ──────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ──────────────────────────────────────────────────────────
-- ENUM TYPES
-- ──────────────────────────────────────────────────────────
CREATE TYPE sport_type AS ENUM (
    'SWIMMING', 'CYCLING', 'RUNNING', 'STRENGTH'
);

CREATE TYPE step_type AS ENUM (
    'WARMUP', 'COOLDOWN', 'INTERVAL', 'RECOVERY',
    'REST', 'REPEAT', 'OTHER'
);

CREATE TYPE duration_type AS ENUM (
    'TIME',              -- segundos
    'DISTANCE',          -- metros
    'REPS',              -- repeticiones (fuerza)
    'OPEN',              -- sin límite (hasta que el atleta avance)
    'HR_LESS_THAN',      -- hasta que FC < valor
    'HR_GREATER_THAN',   -- hasta que FC > valor
    'POWER_LESS_THAN',   -- ciclismo: hasta que pot < valor
    'POWER_GREATER_THAN',-- ciclismo: hasta que pot > valor
    'FIXED_REST'         -- descanso con duración fija
);

CREATE TYPE target_type AS ENUM (
    'OPEN',              -- sin objetivo (RPE libre)
    'SPEED',             -- m/s (natación y running)
    'HEART_RATE',        -- bpm absoluto
    'CADENCE',           -- rpm
    'POWER',             -- vatios absolutos
    'POWER_PCT_FTP',     -- % FTP (se convierte a vatios en runtime)
    'HEART_RATE_PCT',    -- % LTHR (se convierte a bpm en runtime)
    'PACE_PER_KM',       -- seg/km (running) → se convierte a m/s
    'PACE_PER_100M',     -- seg/100m (natación) → se convierte a m/s
    'SWIM_STROKE'        -- tipo de brazada
);

CREATE TYPE sync_status AS ENUM (
    'PENDING', 'QUEUED', 'SYNCING', 'SYNCED', 'FAILED', 'RATE_LIMITED'
);

-- ──────────────────────────────────────────────────────────
-- TABLA: usuarios y tokens Garmin OAuth
-- ──────────────────────────────────────────────────────────
CREATE TABLE garmin_user_tokens (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL UNIQUE,          -- FK a tu tabla de usuarios
    garmin_user_id      TEXT NOT NULL UNIQUE,          -- ID en Garmin Connect
    garmin_display_name TEXT,

    -- OAuth 1.0a (Health API legacy — aún usado en muchos endpoints)
    oauth1_token        TEXT,
    oauth1_token_secret TEXT,                          -- ENCRYPTED en producción

    -- OAuth 2.0 (Training API v2 — recomendado para workouts)
    oauth2_access_token  TEXT,
    oauth2_refresh_token TEXT,
    oauth2_expires_at    TIMESTAMPTZ,
    oauth2_scope         TEXT[],                       -- ['WORKOUT_WRITE', 'SCHEDULE_WRITE', ...]

    -- Métricas del atleta necesarias para conversión de targets
    ftp_watts           SMALLINT   DEFAULT 240,        -- para % FTP → vatios
    lthr_bpm            SMALLINT   DEFAULT 168,        -- para % LTHR → bpm
    css_sec_100m        SMALLINT   DEFAULT 110,        -- para % CSS → seg/100m
    weight_kg           NUMERIC(5,2) DEFAULT 72.0,

    last_sync_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_garmin_tokens_user ON garmin_user_tokens(user_id);

-- ──────────────────────────────────────────────────────────
-- TABLA: sesiones de entrenamiento estructuradas
-- ──────────────────────────────────────────────────────────
CREATE TABLE workouts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    coach_id            UUID NOT NULL,                 -- FK al coach/creador
    athlete_id          UUID NOT NULL,                 -- FK al atleta destino
    sport               sport_type NOT NULL,

    name                TEXT NOT NULL,
    description         TEXT,
    notes_coach         TEXT,                          -- notas privadas del coach
    notes_athlete       TEXT,                          -- instrucciones visibles al atleta

    -- Estimaciones calculadas en tiempo real
    estimated_duration_sec  INT,
    estimated_distance_m    NUMERIC(10,2),
    estimated_tss           NUMERIC(6,2),
    estimated_kcal          INT,

    -- Fecha target en el calendario del atleta
    scheduled_date      DATE,

    -- Estado de sincronización con Garmin
    sync_status         sync_status DEFAULT 'PENDING',
    garmin_workout_id   BIGINT,                        -- ID devuelto por Garmin API
    garmin_schedule_id  BIGINT,                        -- ID del evento en calendario Garmin
    synced_at           TIMESTAMPTZ,
    sync_error          TEXT,
    sync_retry_count    SMALLINT DEFAULT 0,
    sync_next_retry_at  TIMESTAMPTZ,

    -- Raw payload para auditoría
    garmin_payload      JSONB,                         -- JSON enviado a Garmin
    garmin_response     JSONB,                         -- respuesta de Garmin

    is_template         BOOLEAN DEFAULT FALSE,         -- plantilla reutilizable
    template_name       TEXT,

    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW(),
    deleted_at          TIMESTAMPTZ                    -- soft delete
);

CREATE INDEX idx_workouts_athlete        ON workouts(athlete_id);
CREATE INDEX idx_workouts_coach          ON workouts(coach_id);
CREATE INDEX idx_workouts_scheduled_date ON workouts(scheduled_date);
CREATE INDEX idx_workouts_sync_status    ON workouts(sync_status);
CREATE INDEX idx_workouts_sync_retry     ON workouts(sync_next_retry_at)
    WHERE sync_status IN ('PENDING','FAILED','RATE_LIMITED');

-- ──────────────────────────────────────────────────────────
-- TABLA: bloques/steps del entrenamiento
-- ──────────────────────────────────────────────────────────
CREATE TABLE workout_steps (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workout_id      UUID NOT NULL REFERENCES workouts(id) ON DELETE CASCADE,

    step_order      SMALLINT NOT NULL,     -- posición en la sesión (1-based)
    parent_step_id  UUID REFERENCES workout_steps(id),  -- para steps dentro de REPEAT

    step_type       step_type NOT NULL,
    label           TEXT,                  -- nombre del bloque (ej: "Bloque de Series")

    -- DURACIÓN
    duration_type   duration_type NOT NULL,
    duration_value  NUMERIC(10,2),         -- segundos / metros / reps según duration_type

    -- OBJETIVO DE INTENSIDAD
    target_type     target_type NOT NULL DEFAULT 'OPEN',
    target_low      NUMERIC(10,4),         -- límite inferior del rango objetivo
    target_high     NUMERIC(10,4),         -- límite superior del rango objetivo

    -- Si step_type = REPEAT: cuántas veces se repite el bloque
    repeat_count    SMALLINT,

    -- Instrucciones adicionales (para el atleta en el reloj)
    description     TEXT,

    -- Swim-specific
    swim_stroke     TEXT,                  -- FREESTYLE, BACKSTROKE, BREASTSTROKE, BUTTERFLY, DRILL

    created_at      TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT chk_repeat_count CHECK (
        (step_type = 'REPEAT' AND repeat_count IS NOT NULL AND repeat_count > 0)
        OR step_type != 'REPEAT'
    ),
    CONSTRAINT chk_order_positive CHECK (step_order > 0)
);

CREATE INDEX idx_steps_workout    ON workout_steps(workout_id, step_order);
CREATE INDEX idx_steps_parent     ON workout_steps(parent_step_id);

-- ──────────────────────────────────────────────────────────
-- TABLA: cola de sincronización (desacoplada del request)
-- ──────────────────────────────────────────────────────────
CREATE TABLE sync_queue (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workout_id      UUID NOT NULL REFERENCES workouts(id),
    athlete_id      UUID NOT NULL,
    operation       TEXT NOT NULL CHECK (operation IN ('CREATE','UPDATE','DELETE','SCHEDULE','UNSCHEDULE')),
    priority        SMALLINT DEFAULT 5,            -- 1 = alta, 10 = baja
    payload         JSONB,                         -- snapshot del workout al encolar
    status          sync_status DEFAULT 'PENDING',
    attempts        SMALLINT DEFAULT 0,
    max_attempts    SMALLINT DEFAULT 3,
    error_detail    TEXT,
    scheduled_for   TIMESTAMPTZ DEFAULT NOW(),     -- no procesar antes de esta hora
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_queue_pending ON sync_queue(scheduled_for, priority)
    WHERE status IN ('PENDING','RATE_LIMITED');
CREATE INDEX idx_queue_workout ON sync_queue(workout_id);

-- ──────────────────────────────────────────────────────────
-- TABLA: log de auditoría de cada llamada a Garmin API
-- ──────────────────────────────────────────────────────────
CREATE TABLE garmin_api_log (
    id              BIGSERIAL PRIMARY KEY,
    queue_id        UUID REFERENCES sync_queue(id),
    workout_id      UUID REFERENCES workouts(id),
    athlete_id      UUID,
    endpoint        TEXT NOT NULL,
    method          TEXT NOT NULL,
    request_body    JSONB,
    response_status INT,
    response_body   JSONB,
    latency_ms      INT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_api_log_workout   ON garmin_api_log(workout_id);
CREATE INDEX idx_api_log_athlete   ON garmin_api_log(athlete_id);
CREATE INDEX idx_api_log_created   ON garmin_api_log(created_at DESC);

-- ──────────────────────────────────────────────────────────
-- TRIGGER: actualiza updated_at automáticamente
-- ──────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_workouts_updated
    BEFORE UPDATE ON workouts
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_tokens_updated
    BEFORE UPDATE ON garmin_user_tokens
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
