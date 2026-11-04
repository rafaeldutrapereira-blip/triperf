"""Garmin oficial: tablas garmin_oauth_tokens y garmin_oauth_states

Revision ID: v8w9x0y1z2a3
Revises: u7v8w9x0y1z2
Create Date: 2026-11-04
"""
from alembic import op
import sqlalchemy as sa


revision = "v8w9x0y1z2a3"
down_revision = "u7v8w9x0y1z2"
branch_labels = None
depends_on = None


def _exists(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade():
    if not _exists("garmin_oauth_tokens"):
        op.create_table(
            "garmin_oauth_tokens",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
            sa.Column("garmin_user_id", sa.String(), nullable=True),
            sa.Column("access_token", sa.Text(), nullable=False),
            sa.Column("refresh_token", sa.Text(), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("scope", sa.String(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_garmin_oauth_tokens_garmin_user_id", "garmin_oauth_tokens", ["garmin_user_id"])
    if not _exists("garmin_oauth_states"):
        op.create_table(
            "garmin_oauth_states",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("state_hash", sa.String(), nullable=False, unique=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("code_verifier", sa.String(), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_garmin_oauth_states_user_id", "garmin_oauth_states", ["user_id"])


def downgrade():
    for t in ("garmin_oauth_states", "garmin_oauth_tokens"):
        if _exists(t):
            op.drop_table(t)
