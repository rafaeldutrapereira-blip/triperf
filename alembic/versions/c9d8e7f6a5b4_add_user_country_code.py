"""add users.country_code (comunidad — filtro comparar por país)

Revision ID: c9d8e7f6a5b4
Revises: 73420eb748d0
Create Date: 2026-07-17
"""
from alembic import op
import sqlalchemy as sa

revision = 'c9d8e7f6a5b4'
down_revision = '73420eb748d0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('country_code', sa.String(), nullable=True))


def downgrade():
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('country_code')
