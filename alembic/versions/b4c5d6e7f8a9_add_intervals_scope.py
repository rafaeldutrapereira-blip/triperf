"""add users.intervals_scope (scopes OAuth otorgados por intervals.icu)

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-11-06
"""
from alembic import op
import sqlalchemy as sa


revision = "b4c5d6e7f8a9"
down_revision = "a3b4c5d6e7f8"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    cols = [row[1] for row in conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()]
    return column in cols


def upgrade():
    if not _column_exists("users", "intervals_scope"):
        op.add_column("users", sa.Column("intervals_scope", sa.String(), nullable=True))


def downgrade():
    op.drop_column("users", "intervals_scope")
