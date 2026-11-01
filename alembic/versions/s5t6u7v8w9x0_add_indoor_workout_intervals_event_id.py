"""add intervals_event_id to indoor_workouts (reenvio actualiza el evento, S15)

Revision ID: s5t6u7v8w9x0
Revises: r4s5t6u7v8w9
Create Date: 2026-11-01
"""
from alembic import op
import sqlalchemy as sa


revision = "s5t6u7v8w9x0"
down_revision = "r4s5t6u7v8w9"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    cols = [row[1] for row in conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()]
    return column in cols


def upgrade():
    if not _column_exists("indoor_workouts", "intervals_event_id"):
        op.add_column("indoor_workouts", sa.Column("intervals_event_id", sa.String(), nullable=True))


def downgrade():
    op.drop_column("indoor_workouts", "intervals_event_id")
