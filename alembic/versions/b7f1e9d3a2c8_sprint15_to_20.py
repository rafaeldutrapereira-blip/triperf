"""Sprint 15-20: recovery, adaptive, mental, race_results, race_plans, ai_engine_v2

Revision ID: b7f1e9d3a2c8
Revises: a1b2c3d4e5f6
Create Date: 2026-06-29

Covers:
  S15: recovery_scores
  S16: plan_adaptations, weekly_plan_snapshots
  S18: mental_checkins, mental_fatigue_scores, mental_protocol_sessions
  S19: race_results, race_plans
"""
from alembic import op
import sqlalchemy as sa

revision = 'b7f1e9d3a2c8'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Sprint 15: Recovery ─────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS recovery_scores (
            id            TEXT PRIMARY KEY,
            user_id       TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            date_iso      TEXT NOT NULL,
            score         INTEGER NOT NULL,
            level         TEXT NOT NULL,
            color         TEXT,
            hrv_factor    REAL,
            sleep_factor  REAL,
            load_factor   REAL,
            readiness_factor REAL,
            trend         TEXT,
            recommendation TEXT,
            protocol_suggested TEXT,
            calculated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, date_iso)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_rs_user ON recovery_scores(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_rs_date ON recovery_scores(date_iso)")

    # ── Sprint 16: Adaptive ─────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS plan_adaptations (
            id              TEXT PRIMARY KEY,
            user_id         TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            week_start_iso  TEXT NOT NULL,
            original_tss    REAL,
            adapted_tss     REAL,
            adaptation_pct  REAL,
            trigger         TEXT,
            reason          TEXT,
            applied_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, week_start_iso)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_pa_user ON plan_adaptations(user_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS weekly_plan_snapshots (
            id              TEXT PRIMARY KEY,
            user_id         TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            week_start_iso  TEXT NOT NULL,
            planned_tss     REAL,
            actual_tss      REAL,
            ctl_at_start    REAL,
            tsb_at_start    REAL,
            focus           TEXT,
            sessions_json   TEXT,
            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, week_start_iso)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_wps_user ON weekly_plan_snapshots(user_id)")

    # ── Sprint 18: Mental ───────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS mental_checkins (
            id          TEXT PRIMARY KEY,
            user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            date_iso    TEXT NOT NULL,
            anxiety     INTEGER,
            motivation  INTEGER,
            focus       INTEGER,
            confidence  INTEGER,
            mood        INTEGER,
            notes       TEXT,
            logged_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, date_iso)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_mc_user ON mental_checkins(user_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS mental_fatigue_scores (
            id                  TEXT PRIMARY KEY,
            user_id             TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            date_iso            TEXT NOT NULL,
            score               INTEGER NOT NULL,
            level               TEXT NOT NULL,
            color               TEXT,
            checkin_factor      REAL,
            recovery_factor     REAL,
            hrv_factor          REAL,
            stress_factor       REAL,
            signal              TEXT,
            recommendation      TEXT,
            protocol_suggested  TEXT,
            data_completeness   REAL,
            calculated_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, date_iso)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_mfs_user ON mental_fatigue_scores(user_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS mental_protocol_sessions (
            id           TEXT PRIMARY KEY,
            user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            date_iso     TEXT NOT NULL,
            protocol_id  TEXT NOT NULL,
            duration_min INTEGER,
            rating       INTEGER,
            notes        TEXT,
            completed_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_mps_user ON mental_protocol_sessions(user_id)")

    # ── Sprint 19: Race Day Intelligence ────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS race_results (
            id                  TEXT PRIMARY KEY,
            user_id             TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            race_event_id       TEXT REFERENCES race_events(id),
            swim_time_s         INTEGER,
            t1_time_s           INTEGER,
            bike_time_s         INTEGER,
            t2_time_s           INTEGER,
            run_time_s          INTEGER,
            total_time_s        INTEGER,
            avg_power_bike_w    INTEGER,
            avg_hr_bike         INTEGER,
            avg_hr_run          INTEGER,
            avg_pace_run_s_km   INTEGER,
            pacing_score        INTEGER,
            nutrition_score     INTEGER,
            overall_feeling     INTEGER,
            predicted_total_s   INTEGER,
            prediction_error_s  INTEGER,
            dnf                 BOOLEAN DEFAULT 0,
            dnf_reason          TEXT,
            notes               TEXT,
            created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
            garmin_activity_id  TEXT,
            UNIQUE(user_id, race_event_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_rr_user ON race_results(user_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS race_plans (
            id                  TEXT PRIMARY KEY,
            user_id             TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            race_event_id       TEXT REFERENCES race_events(id),
            ctl_at_generation   REAL,
            tsb_at_generation   REAL,
            recovery_score      INTEGER,
            swim_pred_s         INTEGER,
            t1_pred_s           INTEGER,
            bike_pred_s         INTEGER,
            t2_pred_s           INTEGER,
            run_pred_s          INTEGER,
            total_pred_s        INTEGER,
            bike_target_if      REAL,
            bike_target_power   INTEGER,
            run_target_pace     INTEGER,
            run_target_hr       INTEGER,
            nutrition_plan_json TEXT,
            generated_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
            race_date           TEXT,
            UNIQUE(user_id, race_event_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_rp_user ON race_plans(user_id)")


def downgrade() -> None:
    for table in [
        "race_plans", "race_results",
        "mental_protocol_sessions", "mental_fatigue_scores", "mental_checkins",
        "weekly_plan_snapshots", "plan_adaptations",
        "recovery_scores",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {table}")
