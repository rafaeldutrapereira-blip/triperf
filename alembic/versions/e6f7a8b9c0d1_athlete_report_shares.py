"""athlete_report_shares: enlaces de solo lectura al informe del atleta (DRAGDROP-INFORME)

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-11-15
"""
from alembic import op
import sqlalchemy as sa


revision = "e6f7a8b9c0d1"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade():
    if "athlete_report_shares" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "athlete_report_shares",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("coach_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("athlete_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token", sa.String(), nullable=False),
        sa.Column("period_start", sa.String(), nullable=False),
        sa.Column("period_end", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_athlete_report_shares_token", "athlete_report_shares", ["token"], unique=True)
    op.create_index("ix_athlete_report_shares_coach_id", "athlete_report_shares", ["coach_id"])
    op.create_index("ix_athlete_report_shares_athlete_id", "athlete_report_shares", ["athlete_id"])


def downgrade():
    if "athlete_report_shares" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("athlete_report_shares")
