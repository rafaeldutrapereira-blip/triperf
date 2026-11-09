"""Flow: tablas flow_subscriptions y flow_payment_events (FLOW-INTEGRA, BUILD 366)

Revision ID: e0f1a2b3c4d5
Revises: d9e0f1a2b3c4
Create Date: 2026-11-09
"""
from alembic import op
import sqlalchemy as sa


revision = "e0f1a2b3c4d5"
down_revision = "d9e0f1a2b3c4"
branch_labels = None
depends_on = None


def _exists(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade():
    if not _exists("flow_subscriptions"):
        op.create_table(
            "flow_subscriptions",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("product", sa.String(20), nullable=False),
            sa.Column("plan_nivel", sa.String(20), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="pendiente"),
            sa.Column("flow_customer_id", sa.String(), nullable=True),
            sa.Column("flow_subscription_id", sa.String(), nullable=True, unique=True),
            sa.Column("register_token", sa.String(), nullable=True),
            sa.Column("period_start", sa.DateTime(), nullable=True),
            sa.Column("period_end", sa.DateTime(), nullable=True),
            sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_flow_subscriptions_user_id", "flow_subscriptions", ["user_id"])
        op.create_index("ix_flow_subscriptions_flow_customer_id", "flow_subscriptions", ["flow_customer_id"])
        op.create_index("ix_flow_subscriptions_register_token", "flow_subscriptions", ["register_token"])
        op.create_index("ix_flow_sub_user_status", "flow_subscriptions", ["user_id", "status"])
    if not _exists("flow_payment_events"):
        op.create_table(
            "flow_payment_events",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("flow_order", sa.String(), nullable=False, unique=True),
            sa.Column("pay_status", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_flow_payment_events_user_id", "flow_payment_events", ["user_id"])


def downgrade():
    for t in ("flow_payment_events", "flow_subscriptions"):
        if _exists(t):
            op.drop_table(t)
