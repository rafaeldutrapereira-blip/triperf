"""Sprint 27 – workout prescription layer."""
from alembic import op

revision = 'd0e1f2a3b4c5'
down_revision = 'c9e2f4a1b3d7'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS workout_prescriptions (
            id TEXT PRIMARY KEY,
            coach_id TEXT NOT NULL REFERENCES users(id),
            athlete_id TEXT NOT NULL REFERENCES users(id),
            title TEXT NOT NULL,
            description TEXT,
            sport TEXT NOT NULL DEFAULT 'run',
            date_iso TEXT NOT NULL,
            duration_min INTEGER,
            tss_target REAL,
            structure_json TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            prescribed_at DATETIME NOT NULL DEFAULT (datetime('now')),
            completed_at DATETIME
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_wp_athlete_date ON workout_prescriptions(athlete_id, date_iso)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_wp_coach ON workout_prescriptions(coach_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS prescription_feedbacks (
            id TEXT PRIMARY KEY,
            prescription_id TEXT NOT NULL REFERENCES workout_prescriptions(id),
            athlete_id TEXT NOT NULL REFERENCES users(id),
            rpe INTEGER,
            notes TEXT,
            actual_duration_min INTEGER,
            tss_actual REAL,
            feedback_at DATETIME NOT NULL DEFAULT (datetime('now'))
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_pf_prescription ON prescription_feedbacks(prescription_id)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS prescription_feedbacks")
    op.execute("DROP TABLE IF EXISTS workout_prescriptions")
