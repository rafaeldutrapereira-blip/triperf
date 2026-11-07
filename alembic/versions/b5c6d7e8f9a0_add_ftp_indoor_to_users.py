"""add ftp_indoor to users (FTP en rodillo, M1)

Revision ID: b5c6d7e8f9a0
Revises: b4c5d6e7f8a9
Create Date: 2026-11-06
"""
from alembic import op
import sqlalchemy as sa


revision = "b5c6d7e8f9a0"
down_revision = "b4c5d6e7f8a9"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    cols = [row[1] for row in conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()]
    return column in cols


def upgrade():
    # Idempotente y aditiva; NULL = usar el FTP principal
    if not _column_exists("users", "ftp_indoor"):
        op.add_column("users", sa.Column("ftp_indoor", sa.Integer(), nullable=True))


def downgrade():
    if _column_exists("users", "ftp_indoor"):
        with op.batch_alter_table("users") as batch:
            batch.drop_column("ftp_indoor")
