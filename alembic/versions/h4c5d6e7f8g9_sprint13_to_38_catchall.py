"""Sprint 13-38 catchall: tables + columns not yet in Alembic chain.

Revision ID: h4c5d6e7f8g9
Revises: g3b4c5d6e7f8
Create Date: 2026-07-03

Covers tables/columns that were previously managed via:
  - coach_main.py hot-migration block (lines 168-709, now removed)
  - start_coach_api.py::migrate_db() (now removed)

All CREATE TABLE statements use IF NOT EXISTS (idempotent on existing DBs).
ALTER TABLE statements are wrapped in try/except to skip already-present columns.
"""
from alembic import op
import sqlalchemy as sa


revision = 'h4c5d6e7f8g9'
down_revision = 'g3b4c5d6e7f8'
branch_labels = None
depends_on = None


def _safe(sql: str) -> None:
    """Execute SQL, silently ignoring errors (column/table already exists)."""
    try:
        op.execute(sa.text(sql))
    except Exception:
        pass


def upgrade() -> None:
    # ── login_attempts ────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS login_attempts (
            id           TEXT PRIMARY KEY,
            ip           TEXT NOT NULL,
            attempted_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    _safe("CREATE INDEX IF NOT EXISTS ix_login_attempts_ip ON login_attempts(ip)")
    _safe("CREATE INDEX IF NOT EXISTS ix_login_attempts_at ON login_attempts(attempted_at)")

    # ── drip_logs ─────────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS drip_logs (
            id       TEXT PRIMARY KEY,
            user_id  TEXT NOT NULL REFERENCES users(id),
            tag      TEXT NOT NULL,
            sent_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    _safe("CREATE INDEX IF NOT EXISTS ix_drip_logs_user ON drip_logs(user_id)")

    # ── push_subscriptions ────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS push_subscriptions (
            id         TEXT PRIMARY KEY,
            user_id    TEXT NOT NULL REFERENCES users(id),
            endpoint   TEXT NOT NULL,
            p256dh     TEXT NOT NULL,
            auth_key   TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── injury_risk_snapshots ─────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS injury_risk_snapshots (
            id                   TEXT PRIMARY KEY,
            user_id              TEXT NOT NULL REFERENCES users(id),
            date_iso             TEXT NOT NULL,
            risk_score           REAL,
            risk_level           TEXT,
            risk_color           TEXT,
            acwr_score           REAL,
            hrv_score            REAL,
            monotony_score       REAL,
            strain_score         REAL,
            labs_score           REAL,
            acwr                 REAL,
            hrv_last_night       REAL,
            hrv_7d_avg           REAL,
            monotony             REAL,
            strain               REAL,
            ctl                  REAL,
            atl                  REAL,
            tsb                  REAL,
            alerts_json          TEXT,
            recommendations_json TEXT,
            risk_delta           REAL,
            created_at           DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at           DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, date_iso)
        )
    """)
    _safe("CREATE INDEX IF NOT EXISTS ix_injury_risk_user_date ON injury_risk_snapshots(user_id, date_iso)")

    # ── race_events ───────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS race_events (
            id                 TEXT PRIMARY KEY,
            user_id            TEXT NOT NULL REFERENCES users(id),
            name               TEXT NOT NULL,
            date_iso           TEXT NOT NULL,
            distance           TEXT,
            location           TEXT,
            is_goal_race       BOOLEAN DEFAULT 0,
            surface            TEXT,
            pred_swim_sec      INTEGER,
            pred_bike_sec      INTEGER,
            pred_run_sec       INTEGER,
            pred_t1_sec        INTEGER,
            pred_t2_sec        INTEGER,
            pred_total_sec     INTEGER,
            pred_ctl_snapshot  REAL,
            pred_tsb_projected REAL,
            pred_factors_json  TEXT,
            actual_swim_sec    INTEGER,
            actual_bike_sec    INTEGER,
            actual_run_sec     INTEGER,
            actual_t1_sec      INTEGER,
            actual_t2_sec      INTEGER,
            actual_total_sec   INTEGER,
            actual_notes       TEXT,
            is_pr              BOOLEAN DEFAULT 0,
            ai_briefing_text   TEXT,
            ai_briefing_at     DATETIME,
            created_at         DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── training_plans ────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS training_plans (
            id            TEXT PRIMARY KEY,
            coach_id      TEXT NOT NULL REFERENCES users(id),
            athlete_id    TEXT NOT NULL REFERENCES users(id),
            name          TEXT NOT NULL,
            description   TEXT,
            start_date    TEXT NOT NULL,
            end_date      TEXT NOT NULL,
            weeks         INTEGER NOT NULL DEFAULT 16,
            race_id       TEXT,
            goal_ctl      REAL,
            peak_week     INTEGER,
            phase         TEXT,
            template_id   TEXT,
            is_active     BOOLEAN DEFAULT 1,
            is_template   BOOLEAN DEFAULT 0,
            template_name TEXT,
            notes         TEXT,
            created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    _safe("CREATE INDEX IF NOT EXISTS ix_training_plan_user  ON training_plans(athlete_id)")
    _safe("CREATE INDEX IF NOT EXISTS ix_training_plan_coach ON training_plans(coach_id)")

    # ── plan_sessions ─────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS plan_sessions (
            id                  TEXT PRIMARY KEY,
            plan_id             TEXT NOT NULL REFERENCES training_plans(id),
            athlete_id          TEXT NOT NULL REFERENCES users(id),
            date_iso            TEXT NOT NULL,
            week_number         INTEGER,
            day_of_week         INTEGER,
            sport               TEXT NOT NULL DEFAULT 'other',
            title               TEXT,
            description         TEXT,
            duration_min        INTEGER,
            distance_km         REAL,
            tss_planned         REAL,
            zone                TEXT,
            intensity           TEXT,
            garmin_activity_id  TEXT,
            tss_actual          REAL,
            duration_actual_min INTEGER,
            distance_actual_km  REAL,
            completed_at        DATETIME,
            compliance_pct      REAL,
            is_skipped          BOOLEAN DEFAULT 0,
            skip_reason         TEXT,
            coach_note          TEXT,
            athlete_note        TEXT,
            was_adjusted        BOOLEAN DEFAULT 0,
            adjust_reason       TEXT,
            order_in_day        INTEGER DEFAULT 0,
            rpe                 INTEGER,
            perceived_effort    TEXT,
            mood                TEXT,
            feedback_at         DATETIME,
            created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    _safe("CREATE INDEX IF NOT EXISTS ix_plan_session_plan_date ON plan_sessions(plan_id, date_iso)")
    _safe("CREATE INDEX IF NOT EXISTS ix_plan_session_athlete   ON plan_sessions(athlete_id)")
    # plan_sessions RPE columns — for tables that existed before this revision
    _safe("ALTER TABLE plan_sessions ADD COLUMN rpe              INTEGER")
    _safe("ALTER TABLE plan_sessions ADD COLUMN perceived_effort TEXT")
    _safe("ALTER TABLE plan_sessions ADD COLUMN mood             TEXT")
    _safe("ALTER TABLE plan_sessions ADD COLUMN feedback_at      DATETIME")

    # ── Community tables (Sprint 13) ──────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS follows (
            id          TEXT PRIMARY KEY,
            follower_id TEXT NOT NULL REFERENCES users(id),
            followed_id TEXT NOT NULL REFERENCES users(id),
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(follower_id, followed_id)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS community_posts (
            id          TEXT PRIMARY KEY,
            user_id     TEXT NOT NULL REFERENCES users(id),
            activity_id TEXT REFERENCES garmin_activities(id),
            post_type   TEXT NOT NULL DEFAULT 'activity',
            title       TEXT,
            body        TEXT,
            visibility  TEXT NOT NULL DEFAULT 'followers',
            sport       TEXT,
            dist_km     REAL,
            dur_min     REAL,
            tss         REAL,
            ctl_day     REAL,
            tsb_day     REAL,
            rpe         INTEGER,
            card_image  TEXT,
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS kudos (
            id         TEXT PRIMARY KEY,
            post_id    TEXT NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE,
            user_id    TEXT NOT NULL REFERENCES users(id),
            kudo_type  TEXT NOT NULL DEFAULT 'power',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(post_id, user_id, kudo_type)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id         TEXT PRIMARY KEY,
            post_id    TEXT NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE,
            user_id    TEXT NOT NULL REFERENCES users(id),
            parent_id  TEXT REFERENCES comments(id),
            body       TEXT NOT NULL,
            deleted_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS community_groups (
            id          TEXT PRIMARY KEY,
            owner_id    TEXT NOT NULL REFERENCES users(id),
            name        TEXT NOT NULL UNIQUE,
            description TEXT,
            sport       TEXT DEFAULT 'triathlon',
            level       TEXT DEFAULT 'open',
            is_private  INTEGER DEFAULT 0,
            city        TEXT,
            country     TEXT,
            invite_code TEXT,
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS community_group_members (
            id        TEXT PRIMARY KEY,
            group_id  TEXT NOT NULL REFERENCES community_groups(id) ON DELETE CASCADE,
            user_id   TEXT NOT NULL REFERENCES users(id),
            role      TEXT NOT NULL DEFAULT 'member',
            joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(group_id, user_id)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS challenges (
            id          TEXT PRIMARY KEY,
            group_id    TEXT NOT NULL REFERENCES community_groups(id) ON DELETE CASCADE,
            creator_id  TEXT NOT NULL REFERENCES users(id),
            name        TEXT NOT NULL,
            description TEXT,
            metric      TEXT NOT NULL DEFAULT 'km',
            sport       TEXT DEFAULT 'all',
            target      REAL NOT NULL,
            start_date  TEXT NOT NULL,
            end_date    TEXT NOT NULL,
            is_active   INTEGER DEFAULT 1,
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS challenge_entries (
            id           TEXT PRIMARY KEY,
            challenge_id TEXT NOT NULL REFERENCES challenges(id) ON DELETE CASCADE,
            user_id      TEXT NOT NULL REFERENCES users(id),
            progress     REAL DEFAULT 0,
            last_updated DATETIME,
            UNIQUE(challenge_id, user_id)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS community_notifications (
            id         TEXT PRIMARY KEY,
            user_id    TEXT NOT NULL REFERENCES users(id),
            actor_id   TEXT REFERENCES users(id),
            notif_type TEXT NOT NULL,
            post_id    TEXT REFERENCES community_posts(id) ON DELETE SET NULL,
            group_id   TEXT REFERENCES community_groups(id) ON DELETE SET NULL,
            body       TEXT,
            read_at    DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── blood_lab_alerts ──────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS blood_lab_alerts (
            id               TEXT PRIMARY KEY,
            user_id          TEXT NOT NULL REFERENCES users(id),
            exam_id          TEXT NOT NULL REFERENCES blood_lab_exams(id),
            marker_key       TEXT NOT NULL,
            severity         TEXT NOT NULL,
            title            TEXT NOT NULL,
            body             TEXT,
            correlation_note TEXT,
            dismissed_at     DATETIME,
            created_at       DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Column additions: users ───────────────────────────────────────────────
    for col_sql in [
        "ALTER TABLE users ADD COLUMN strava_access_token    TEXT",
        "ALTER TABLE users ADD COLUMN strava_refresh_token   TEXT",
        "ALTER TABLE users ADD COLUMN strava_athlete_id      TEXT",
        "ALTER TABLE users ADD COLUMN strava_token_expires_at DATETIME",
        "ALTER TABLE users ADD COLUMN totp_backup_hash       TEXT",
        "ALTER TABLE users ADD COLUMN last_device_hash       TEXT",
        "ALTER TABLE users ADD COLUMN stripe_customer_id     TEXT",
        "ALTER TABLE users ADD COLUMN gdpr_consent_at        DATETIME",
        "ALTER TABLE users ADD COLUMN gdpr_consent_ip        TEXT",
        "ALTER TABLE users ADD COLUMN notif_email_weekly     BOOLEAN DEFAULT 1",
        "ALTER TABLE users ADD COLUMN notif_email_workout    BOOLEAN DEFAULT 1",
        "ALTER TABLE users ADD COLUMN notif_push_wellness    BOOLEAN DEFAULT 1",
        "ALTER TABLE users ADD COLUMN ftp                    INTEGER",
        "ALTER TABLE users ADD COLUMN height_cm              INTEGER",
        "ALTER TABLE users ADD COLUMN fcmax                  INTEGER",
    ]:
        _safe(col_sql)

    # ── Column additions: garmin_activities ───────────────────────────────────
    for col_sql in [
        "ALTER TABLE garmin_activities ADD COLUMN swolf           REAL",
        "ALTER TABLE garmin_activities ADD COLUMN avg_cadence_spm REAL",
        "ALTER TABLE garmin_activities ADD COLUMN pool_length_m   INTEGER",
        "ALTER TABLE garmin_activities ADD COLUMN photo_path      TEXT",
    ]:
        _safe(col_sql)

    # ── Column additions: blood_lab_exams ─────────────────────────────────────
    for col_sql in [
        "ALTER TABLE blood_lab_exams ADD COLUMN notes              TEXT",
        "ALTER TABLE blood_lab_exams ADD COLUMN ai_interpretation  TEXT",
        "ALTER TABLE blood_lab_exams ADD COLUMN ai_interpreted_at  DATETIME",
    ]:
        _safe(col_sql)

    # ── Column additions: assigned_workouts ───────────────────────────────────
    _safe("ALTER TABLE assigned_workouts ADD COLUMN coach_comment TEXT")


def downgrade() -> None:
    for table in [
        "blood_lab_alerts",
        "community_notifications", "challenge_entries", "challenges",
        "community_group_members", "community_groups",
        "comments", "kudos", "community_posts", "follows",
        "plan_sessions", "training_plans", "race_events",
        "injury_risk_snapshots", "push_subscriptions",
        "drip_logs", "login_attempts",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {table}")
