"""add last_login_at, stripe_subscription_id, trial_end_at to users

Revision ID: f48d3f06f38e
Revises: h4c5d6e7f8g9
Create Date: 2026-07-04

Migración quirúrgica — solo agrega las 3 columnas nuevas identificadas en el audit LICB.
Usa _column_exists() para ser idempotente (segura de re-ejecutar).
"""
from alembic import op
import sqlalchemy as sa


revision = 'f48d3f06f38e'
down_revision = 'h4c5d6e7f8g9'
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    cols = [row[1] for row in conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()]
    return column in cols


def upgrade() -> None:
    if not _column_exists("users", "last_login_at"):
        op.add_column("users", sa.Column("last_login_at", sa.DateTime(), nullable=True))

    if not _column_exists("users", "stripe_subscription_id"):
        op.add_column("users", sa.Column("stripe_subscription_id", sa.String(), nullable=True))

    if not _column_exists("users", "trial_end_at"):
        op.add_column("users", sa.Column("trial_end_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("trial_end_at")
        batch_op.drop_column("stripe_subscription_id")
        batch_op.drop_column("last_login_at")
