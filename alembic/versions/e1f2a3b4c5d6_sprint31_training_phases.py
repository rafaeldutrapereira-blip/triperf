"""Sprint 31 — Season Periodization: training_phases table.

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa

revision     = 'e1f2a3b4c5d6'
down_revision = 'd0e1f2a3b4c5'
branch_labels = None
depends_on    = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS training_phases (
            id                TEXT PRIMARY KEY,
            coach_id          TEXT NOT NULL REFERENCES users(id),
            athlete_id        TEXT NOT NULL REFERENCES users(id),
            phase_type        TEXT NOT NULL,
            label             TEXT,
            start_date        TEXT NOT NULL,
            end_date          TEXT NOT NULL,
            ctl_target        REAL,
            tss_weekly_target REAL,
            notes             TEXT,
            created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_tp_athlete_dates ON training_phases (athlete_id, start_date)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_tp_coach ON training_phases (coach_id)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS training_phases")
