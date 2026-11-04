"""P0: tabla web_handoffs (puente app -> web, token de un solo uso + contador por destino)

Revision ID: u7v8w9x0y1z2
Revises: t6u7v8w9x0y1
Create Date: 2026-11-04
"""
from alembic import op
import sqlalchemy as sa


revision = "u7v8w9x0y1z2"
down_revision = "t6u7v8w9x0y1"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade():
    if _table_exists("web_handoffs"):
        return
    op.create_table(
        "web_handoffs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("token_hash", sa.String(), nullable=False, unique=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("destino", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_web_handoffs_user_id", "web_handoffs", ["user_id"])
    op.create_index("ix_web_handoffs_destino", "web_handoffs", ["destino"])


def downgrade():
    if _table_exists("web_handoffs"):
        op.drop_table("web_handoffs")
