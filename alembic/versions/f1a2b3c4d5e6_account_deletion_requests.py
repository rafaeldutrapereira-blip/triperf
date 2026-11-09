"""Registro de solicitudes de eliminacion de cuenta (CUENTA-BORRADO, BUILD 367)

Revision ID: f1a2b3c4d5e6
Revises: e0f1a2b3c4d5
Create Date: 2026-11-09
"""
from alembic import op
import sqlalchemy as sa


revision = "f1a2b3c4d5e6"
down_revision = "e0f1a2b3c4d5"
branch_labels = None
depends_on = None


def upgrade():
    if "account_deletion_requests" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "account_deletion_requests",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_ref", sa.String(16), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(12), nullable=False, server_default="pendiente"),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.Column("purge_after", sa.DateTime(), nullable=False),
        sa.Column("deadline_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(200), nullable=True),
        sa.Column("summary_json", sa.Text(), nullable=True),
    )
    op.create_index("ix_account_deletion_requests_user_ref", "account_deletion_requests", ["user_ref"])
    op.create_index("ix_account_deletion_requests_user_id", "account_deletion_requests", ["user_id"])


def downgrade():
    op.drop_table("account_deletion_requests")
