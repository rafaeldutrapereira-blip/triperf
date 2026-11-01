"""add intervals.icu oauth columns to users (envio de workouts al reloj, S6)

Revision ID: r4s5t6u7v8w9
Revises: q3r4s5t6u7v8
Create Date: 2026-11-01
"""
from alembic import op
import sqlalchemy as sa


revision = "r4s5t6u7v8w9"
down_revision = "q3r4s5t6u7v8"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    cols = [row[1] for row in conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()]
    return column in cols


def upgrade():
    if not _column_exists("users", "intervals_access_token"):
        op.add_column("users", sa.Column("intervals_access_token", sa.Text(), nullable=True))
    if not _column_exists("users", "intervals_athlete_id"):
        op.add_column("users", sa.Column("intervals_athlete_id", sa.String(), nullable=True))
    if not _column_exists("users", "intervals_connected_at"):
        op.add_column("users", sa.Column("intervals_connected_at", sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column("users", "intervals_connected_at")
    op.drop_column("users", "intervals_athlete_id")
    op.drop_column("users", "intervals_access_token")
