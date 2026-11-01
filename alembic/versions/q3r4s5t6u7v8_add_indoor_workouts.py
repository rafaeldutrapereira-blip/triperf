"""add indoor_workouts (workouts propios del atleta, S4)

Revision ID: q3r4s5t6u7v8
Revises: p2q3r4s5t6u7
Create Date: 2026-11-01
"""
from alembic import op
import sqlalchemy as sa


revision = "q3r4s5t6u7v8"
down_revision = "p2q3r4s5t6u7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "indoor_workouts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("sport", sa.String(), nullable=False, server_default="bike"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("planned_date", sa.String(10), nullable=True),
        sa.Column("blocks_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("legacy_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("user_id", "legacy_id", name="uq_indoor_workouts_user_legacy"),
    )
    op.create_index("ix_indoor_workouts_user", "indoor_workouts", ["user_id"])


def downgrade():
    op.drop_index("ix_indoor_workouts_user", table_name="indoor_workouts")
    op.drop_table("indoor_workouts")
