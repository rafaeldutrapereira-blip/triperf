"""intervals.icu: estado honesto de la conexion (invalida / ultima sync)

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-11-11
"""
from alembic import op
import sqlalchemy as sa


revision = "b3c4d5e6f7a8"
down_revision = "a2b3c4d5e6f7"
branch_labels = None
depends_on = None

_COLS = ("intervals_invalid_at", "intervals_last_sync_at")


def _cols() -> set:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("users")}


def upgrade():
    have = _cols()
    for c in _COLS:
        if c not in have:
            op.add_column("users", sa.Column(c, sa.DateTime(), nullable=True))


def downgrade():
    have = _cols()
    for c in _COLS:
        if c in have:
            with op.batch_alter_table("users") as b:
                b.drop_column(c)
