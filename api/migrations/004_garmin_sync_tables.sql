-- Migration 004: Tablas para sync histórico Garmin por atleta
-- Ejecutar manualmente: sqlite3 data/labx_coach.db < api/migrations/004_garmin_sync_tables.sql
-- O en PostgreSQL: psql $DATABASE_URL -f api/migrations/004_garmin_sync_tables.sql

CREATE TABLE IF NOT EXISTS garmin_activities (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id),
    activity_id TEXT NOT NULL,
    name        TEXT,
    sport       TEXT,
    date_iso    TEXT NOT NULL,
    date_label  TEXT,
    dur_min     INTEGER DEFAULT 0,
    dist_km     REAL    DEFAULT 0.0,
    avg_hr      INTEGER,
    avg_power   INTEGER,
    pace_str    TEXT,
    swim_pace   TEXT,
    calories    INTEGER,
    elev_m      REAL,
    tss         REAL    DEFAULT 0.0,
    icon        TEXT    DEFAULT '🏅',
    color       TEXT    DEFAULT 'rgba(127,179,204,.08)',
    stroke      TEXT    DEFAULT 'var(--muted)',
    synced_at   TEXT    DEFAULT (datetime('now')),
    CONSTRAINT uq_garmin_act UNIQUE (user_id, activity_id)
);

CREATE INDEX IF NOT EXISTS ix_garmin_act_user_date
    ON garmin_activities (user_id, date_iso);

CREATE TABLE IF NOT EXISTS garmin_training_load (
    id       TEXT PRIMARY KEY,
    user_id  TEXT NOT NULL REFERENCES users(id),
    date_iso TEXT NOT NULL,
    ctl      REAL DEFAULT 0.0,
    atl      REAL DEFAULT 0.0,
    tsb      REAL DEFAULT 0.0,
    tss      REAL DEFAULT 0.0,
    CONSTRAINT uq_garmin_load UNIQUE (user_id, date_iso)
);

CREATE INDEX IF NOT EXISTS ix_garmin_training_load_user
    ON garmin_training_load (user_id);

CREATE TABLE IF NOT EXISTS garmin_sync_status (
    id               TEXT PRIMARY KEY,
    user_id          TEXT NOT NULL UNIQUE REFERENCES users(id),
    status           TEXT DEFAULT 'never',
    last_sync_at     TEXT,
    activities_total INTEGER DEFAULT 0,
    error            TEXT
);

CREATE INDEX IF NOT EXISTS ix_garmin_sync_status_user
    ON garmin_sync_status (user_id);
