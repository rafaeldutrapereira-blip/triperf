"""Polar/Wahoo OAuth: tablas provider_connections y provider_oauth_states

Revision ID: x0y1z2a3b4c5
Revises: w9x0y1z2a3b4
Create Date: 2026-11-05
"""
from alembic import op
import sqlalchemy as sa


revision = "x0y1z2a3b4c5"
down_revision = "w9x0y1z2a3b4"
branch_labels = None
depends_on = None


def _exists(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade():
    if not _exists("provider_connections"):
        op.create_table(
            "provider_connections",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("provider", sa.String(20), nullable=False),
            sa.Column("access_token", sa.Text(), nullable=False),
            sa.Column("refresh_token", sa.Text(), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("external_user_id", sa.String(), nullable=True),
            sa.Column("member_id", sa.String(), nullable=True),
            sa.Column("scope", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("user_id", "provider", name="uq_provider_conn_user_provider"),
        )
        op.create_index("ix_provider_connections_user_id", "provider_connections", ["user_id"])
    if not _exists("provider_oauth_states"):
        op.create_table(
            "provider_oauth_states",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("state_hash", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("provider", sa.String(20), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_provider_oauth_states_state_hash", "provider_oauth_states", ["state_hash"])


def downgrade():
    for t in ("provider_oauth_states", "provider_connections"):
        if _exists(t):
            op.drop_table(t)
