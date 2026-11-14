"""assigned_workouts: estado del push a intervals.icu (PUSH-INTERVALS)

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-11-14
"""
from alembic import op
import sqlalchemy as sa


revision = "c4d5e6f7a8b9"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None

_COLS = (
    ("intervals_push_status", sa.String()),
    ("intervals_push_error", sa.Text()),
    ("intervals_push_at", sa.DateTime()),
    ("intervals_push_event_id", sa.String()),
)


def _have() -> set:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("assigned_workouts")}


def upgrade():
    have = _have()
    for name, typ in _COLS:
        if name not in have:
            op.add_column("assigned_workouts", sa.Column(name, typ, nullable=True))


def downgrade():
    have = _have()
    with op.batch_alter_table("assigned_workouts") as b:
        for name, _ in _COLS:
            if name in have:
                b.drop_column(name)
