"""CQ7: tabla own_plan_sessions (plan propio del atleta, antes en localStorage)

Revision ID: w9x0y1z2a3b4
Revises: v8w9x0y1z2a3
Create Date: 2026-11-04
"""
from alembic import op
import sqlalchemy as sa


revision = "w9x0y1z2a3b4"
down_revision = "v8w9x0y1z2a3"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade():
    if _table_exists("own_plan_sessions"):
        return
    op.create_table(
        "own_plan_sessions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("date_iso", sa.String(10), nullable=False),
        sa.Column("sport", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("dur_min", sa.Integer(), nullable=True),
        sa.Column("dist_km", sa.Float(), nullable=True),
        sa.Column("tss", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("indoor_workout_id", sa.String(), nullable=True),
        sa.Column("legacy_id", sa.String(), nullable=True),
        sa.Column("data_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("user_id", "legacy_id", name="uq_own_plan_sessions_user_legacy"),
    )
    op.create_index("ix_own_plan_sessions_user_date", "own_plan_sessions", ["user_id", "date_iso"])


def downgrade():
    if _table_exists("own_plan_sessions"):
        op.drop_table("own_plan_sessions")
