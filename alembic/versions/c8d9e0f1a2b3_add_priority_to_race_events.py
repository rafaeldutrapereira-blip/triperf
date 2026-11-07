"""add priority a race_events (A|B|C, CARRERAS-PERFIL)

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-11-07
"""
from alembic import op
import sqlalchemy as sa


revision = "c8d9e0f1a2b3"
down_revision = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    cols = [row[1] for row in conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()]
    return column in cols


def upgrade():
    if not _column_exists("race_events", "priority"):
        op.add_column("race_events", sa.Column("priority", sa.String(), nullable=True))


def downgrade():
    if _column_exists("race_events", "priority"):
        with op.batch_alter_table("race_events") as b:
            b.drop_column("priority")
