"""add sexo to users (rangos de Blood Labs, W11)

Revision ID: t6u7v8w9x0y1
Revises: s5t6u7v8w9x0
Create Date: 2026-11-02
"""
from alembic import op
import sqlalchemy as sa


revision = "t6u7v8w9x0y1"
down_revision = "s5t6u7v8w9x0"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    cols = [row[1] for row in conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()]
    return column in cols


def upgrade():
    # Idempotente; NULL = sin declarar (nunca se asume un sexo por defecto)
    if not _column_exists("users", "sexo"):
        op.add_column("users", sa.Column("sexo", sa.String(), nullable=True))


def downgrade():
    if _column_exists("users", "sexo"):
        with op.batch_alter_table("users") as batch:
            batch.drop_column("sexo")
