"""coach_alert_rules: umbrales de alerta configurables por coach (COACH-TABLERO)

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-11-14
"""
from alembic import op
import sqlalchemy as sa


revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def _exists() -> bool:
    return "coach_alert_rules" in sa.inspect(op.get_bind()).get_table_names()


def upgrade():
    if _exists():
        return
    op.create_table(
        "coach_alert_rules",
        sa.Column("coach_id", sa.String(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("fatigue", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("soreness", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("rpe", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("window_hours", sa.Integer(), nullable=False, server_default="48"),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )


def downgrade():
    if _exists():
        op.drop_table("coach_alert_rules")