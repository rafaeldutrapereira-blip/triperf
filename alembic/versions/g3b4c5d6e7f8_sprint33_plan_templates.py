"""Sprint 33 — Training Plan Templates: plan_templates + plan_template_weeks tables.

Revision ID: g3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-07-02
"""
from alembic import op

revision      = 'g3b4c5d6e7f8'
down_revision = 'f2a3b4c5d6e7'
branch_labels = None
depends_on    = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS plan_templates (
            id            TEXT PRIMARY KEY,
            coach_id      TEXT REFERENCES users(id),
            name          TEXT NOT NULL,
            sport         TEXT NOT NULL DEFAULT 'triathlon',
            distance_type TEXT,
            weeks         INTEGER NOT NULL,
            difficulty    TEXT,
            description   TEXT,
            is_public     INTEGER NOT NULL DEFAULT 0,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_pt_coach       ON plan_templates (coach_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_pt_sport_dist  ON plan_templates (sport, distance_type)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS plan_template_weeks (
            id            TEXT PRIMARY KEY,
            template_id   TEXT NOT NULL REFERENCES plan_templates(id) ON DELETE CASCADE,
            week_num      INTEGER NOT NULL,
            phase_type    TEXT,
            label         TEXT,
            tss_target    REAL,
            hours_target  REAL,
            sessions_json TEXT,
            notes         TEXT
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_ptw_template ON plan_template_weeks (template_id)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS plan_template_weeks")
    op.execute("DROP TABLE IF EXISTS plan_templates")
