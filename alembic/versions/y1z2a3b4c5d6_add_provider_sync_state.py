"""provider_connections: estado del ultimo sync (Sprint 56 paso 2)

Revision ID: y1z2a3b4c5d6
Revises: x0y1z2a3b4c5
Create Date: 2026-11-05
"""
from alembic import op
import sqlalchemy as sa


revision = "y1z2a3b4c5d6"
down_revision = "x0y1z2a3b4c5"
branch_labels = None
depends_on = None

_COLS = [
    ("last_sync_at", sa.DateTime()),
    ("last_sync_status", sa.String(10)),
    ("last_sync_error", sa.String()),
    ("last_sync_saved", sa.Integer()),
]


def _have() -> set:
    insp = sa.inspect(op.get_bind())
    if "provider_connections" not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns("provider_connections")}


def upgrade():
    have = _have()
    if not have:
        return
    for name, typ in _COLS:
        if name not in have:
            op.add_column("provider_connections", sa.Column(name, typ, nullable=True))


def downgrade():
    have = _have()
    for name, _ in reversed(_COLS):
        if name in have:
            with op.batch_alter_table("provider_connections") as b:
                b.drop_column(name)
