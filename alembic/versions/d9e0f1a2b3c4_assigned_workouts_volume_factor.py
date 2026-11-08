"""COACH-VARIANTES: factor de volumen y valores escalados en assigned_workouts (aditiva)

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-11-08
"""
from alembic import op
import sqlalchemy as sa


revision = "d9e0f1a2b3c4"
down_revision = "c8d9e0f1a2b3"
branch_labels = None
depends_on = None

_COLS = [
    ("volume_factor", sa.Float()),
    ("dur_min_scaled", sa.Integer()),
    ("dist_km_scaled", sa.Float()),
    ("blocks_json_scaled", sa.Text()),
]


def _cols():
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("assigned_workouts")}


def upgrade():
    have = _cols()
    for name, typ in _COLS:
        if name not in have:
            op.add_column("assigned_workouts", sa.Column(name, typ, nullable=True))


def downgrade():
    have = _cols()
    with op.batch_alter_table("assigned_workouts") as b:
        for name, _ in _COLS:
            if name in have:
                b.drop_column(name)
