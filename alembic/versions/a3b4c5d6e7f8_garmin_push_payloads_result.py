"""Garmin oficial: processed_at/error en garmin_push_payloads (ingestor fase B)

Revision ID: a3b4c5d6e7f8
Revises: z2a3b4c5d6e7
Create Date: 2026-11-06
"""
from alembic import op
import sqlalchemy as sa


revision = "a3b4c5d6e7f8"
down_revision = "z2a3b4c5d6e7"
branch_labels = None
depends_on = None


def _cols() -> set:
    insp = sa.inspect(op.get_bind())
    if "garmin_push_payloads" not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns("garmin_push_payloads")}


def upgrade():
    cols = _cols()
    if not cols:
        return
    if "processed_at" not in cols:
        op.add_column("garmin_push_payloads", sa.Column("processed_at", sa.DateTime(), nullable=True))
    if "error" not in cols:
        op.add_column("garmin_push_payloads", sa.Column("error", sa.String(300), nullable=True))


def downgrade():
    cols = _cols()
    with op.batch_alter_table("garmin_push_payloads") as b:
        if "error" in cols:
            b.drop_column("error")
        if "processed_at" in cols:
            b.drop_column("processed_at")
