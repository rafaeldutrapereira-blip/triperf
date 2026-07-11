"""add missing user columns: totp_backup_hash, last_device_hash, stripe_customer_id

Revision ID: b9c0d1e2f3a4
Revises: f48d3f06f38e
Create Date: 2026-07-04

Migración quirúrgica — agrega 3 columnas que existen en models.py pero no en el DB.
Usa _column_exists() para ser idempotente.
"""
from alembic import op
import sqlalchemy as sa


revision = 'b9c0d1e2f3a4'
down_revision = 'f48d3f06f38e'
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    cols = [row[1] for row in conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()]
    return column in cols


def _index_exists(index_name: str) -> bool:
    conn = op.get_bind()
    rows = conn.execute(sa.text(f"SELECT name FROM sqlite_master WHERE type='index' AND name='{index_name}'")).fetchall()
    return len(rows) > 0


def upgrade() -> None:
    if not _column_exists("users", "totp_backup_hash"):
        op.add_column("users", sa.Column("totp_backup_hash", sa.Text(), nullable=True))

    if not _column_exists("users", "last_device_hash"):
        op.add_column("users", sa.Column("last_device_hash", sa.String(), nullable=True))

    if not _column_exists("users", "stripe_customer_id"):
        op.add_column("users", sa.Column("stripe_customer_id", sa.String(), nullable=True))
        if not _index_exists("ix_users_stripe_customer_id"):
            op.create_index("ix_users_stripe_customer_id", "users", ["stripe_customer_id"])


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("totp_backup_hash")
        batch_op.drop_column("last_device_hash")
        if _index_exists("ix_users_stripe_customer_id"):
            batch_op.drop_index("ix_users_stripe_customer_id")
        batch_op.drop_column("stripe_customer_id")
