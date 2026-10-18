"""add entitlements and ai_usage_daily (B12 addons)

Tablas para los addons vendibles (entitlements) y la cuota diaria del
Asistente IA (ai_usage_daily). No modifica datos existentes.

Revision ID: p2q3r4s5t6u7
Revises: b8e2c4d6f1a9
Create Date: 2026-10-18
"""
from alembic import op
import sqlalchemy as sa


revision = "p2q3r4s5t6u7"
down_revision = "b8e2c4d6f1a9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "entitlements",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("addon_id", sa.String(40), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("stripe_subscription_id", sa.String(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_entitlements_user_id", "entitlements", ["user_id"])
    op.create_index("ix_entitlements_stripe_subscription_id", "entitlements", ["stripe_subscription_id"])

    op.create_table(
        "ai_usage_daily",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("date_iso", sa.String(10), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("user_id", "date_iso", name="uq_ai_usage_user_day"),
    )
    op.create_index("ix_ai_usage_daily_user_id", "ai_usage_daily", ["user_id"])


def downgrade():
    op.drop_index("ix_ai_usage_daily_user_id", table_name="ai_usage_daily")
    op.drop_table("ai_usage_daily")
    op.drop_index("ix_entitlements_stripe_subscription_id", table_name="entitlements")
    op.drop_index("ix_entitlements_user_id", table_name="entitlements")
    op.drop_table("entitlements")
