"""Marca de actividades duplicadas (PILA 374 DEDUPE)

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-11-09
"""
from alembic import op
import sqlalchemy as sa


revision = "a2b3c4d5e6f7"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def _cols():
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("garmin_activities")}


def upgrade():
    cols = _cols()
    with op.batch_alter_table("garmin_activities") as b:
        if "duplicate_of_id" not in cols:
            b.add_column(sa.Column("duplicate_of_id", sa.String(), nullable=True))
        if "duplicate_reason" not in cols:
            b.add_column(sa.Column("duplicate_reason", sa.String(), nullable=True))
    idx = {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("garmin_activities")}
    if "ix_garmin_activities_duplicate_of_id" not in idx:
        op.create_index("ix_garmin_activities_duplicate_of_id", "garmin_activities", ["duplicate_of_id"])


def downgrade():
    op.drop_index("ix_garmin_activities_duplicate_of_id", table_name="garmin_activities")
    with op.batch_alter_table("garmin_activities") as b:
        b.drop_column("duplicate_reason")
        b.drop_column("duplicate_of_id")
