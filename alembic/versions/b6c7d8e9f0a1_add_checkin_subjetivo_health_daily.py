"""add check-in subjetivo (energia, animo, dolor_muscular, estres) a garmin_health_daily (M2)

Revision ID: b6c7d8e9f0a1
Revises: b5c6d7e8f9a0
Create Date: 2026-11-06
"""
from alembic import op
import sqlalchemy as sa


revision = "b6c7d8e9f0a1"
down_revision = "b5c6d7e8f9a0"
branch_labels = None
depends_on = None

_COLS = ("energia", "animo", "dolor_muscular", "estres")


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    cols = [row[1] for row in conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()]
    return column in cols


def upgrade():
    for c in _COLS:
        if not _column_exists("garmin_health_daily", c):
            op.add_column("garmin_health_daily", sa.Column(c, sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table("garmin_health_daily") as batch:
        for c in _COLS:
            if _column_exists("garmin_health_daily", c):
                batch.drop_column(c)
