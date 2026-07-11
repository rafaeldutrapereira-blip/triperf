"""Sprint 32 — Performance Benchmarks & Training Zones: performance_benchmarks table.

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa

revision     = 'f2a3b4c5d6e7'
down_revision = 'e1f2a3b4c5d6'
branch_labels = None
depends_on    = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS performance_benchmarks (
            id                      TEXT PRIMARY KEY,
            athlete_id              TEXT NOT NULL REFERENCES users(id),
            coach_id                TEXT REFERENCES users(id),
            sport                   TEXT NOT NULL,
            ftp_watts               INTEGER,
            threshold_pace_sec_km   INTEGER,
            threshold_pace_sec_100m INTEGER,
            max_hr                  INTEGER,
            lthr                    INTEGER,
            weight_kg               REAL,
            test_date               TEXT NOT NULL,
            test_type               TEXT,
            notes                   TEXT,
            created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_pb_athlete_sport ON performance_benchmarks (athlete_id, sport)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_pb_athlete_date  ON performance_benchmarks (athlete_id, test_date)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS performance_benchmarks")
