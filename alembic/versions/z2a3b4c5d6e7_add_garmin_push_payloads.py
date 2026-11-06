"""Garmin oficial: bandeja de entrada garmin_push_payloads (ingestor fase A)

Revision ID: z2a3b4c5d6e7
Revises: y1z2a3b4c5d6
Create Date: 2026-11-05
"""
from alembic import op
import sqlalchemy as sa


revision = "z2a3b4c5d6e7"
down_revision = "y1z2a3b4c5d6"
branch_labels = None
depends_on = None


def _exists(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade():
    if not _exists("garmin_push_payloads"):
        op.create_table(
            "garmin_push_payloads",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("received_at", sa.DateTime(), nullable=True),
            sa.Column("payload_type", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=True),
            sa.Column("payload_json", sa.Text(), nullable=False),
            sa.Column("processed", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        op.create_index("ix_garmin_push_payloads_received_at", "garmin_push_payloads", ["received_at"])
        op.create_index("ix_garmin_push_payloads_payload_type", "garmin_push_payloads", ["payload_type"])
        op.create_index("ix_garmin_push_payloads_user_id", "garmin_push_payloads", ["user_id"])


def downgrade():
    if _exists("garmin_push_payloads"):
        op.drop_table("garmin_push_payloads")
