"""add share_token a training_plans (link compartible de solo lectura, M4)

Revision ID: b7c8d9e0f1a2
Revises: b6c7d8e9f0a1
Create Date: 2026-11-06
"""
from alembic import op
import sqlalchemy as sa


revision = "b7c8d9e0f1a2"
down_revision = "b6c7d8e9f0a1"
branch_labels = None
depends_on = None

_IDX = "ix_training_plans_share_token"


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    cols = [row[1] for row in conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()]
    return column in cols


def upgrade():
    if not _column_exists("training_plans", "share_token"):
        op.add_column("training_plans", sa.Column("share_token", sa.String(), nullable=True))
    op.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS {_IDX} ON training_plans (share_token)")


def downgrade():
    op.execute(f"DROP INDEX IF EXISTS {_IDX}")
    with op.batch_alter_table("training_plans") as batch:
        if _column_exists("training_plans", "share_token"):
            batch.drop_column("share_token")
