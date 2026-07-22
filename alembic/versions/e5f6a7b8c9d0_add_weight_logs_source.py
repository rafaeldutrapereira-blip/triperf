"""add weight_logs.source (manual vs garmin — para no pisar entradas manuales)

Revision ID: e5f6a7b8c9d0
Revises: d1e2f3a4b5c7
Create Date: 2026-07-21
"""
from alembic import op
import sqlalchemy as sa

revision = 'e5f6a7b8c9d0'
down_revision = 'd1e2f3a4b5c7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('weight_logs') as batch_op:
        batch_op.add_column(sa.Column('source', sa.String(), nullable=False, server_default='manual'))


def downgrade():
    with op.batch_alter_table('weight_logs') as batch_op:
        batch_op.drop_column('source')
