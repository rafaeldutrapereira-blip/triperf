"""add users.community_share_prefs (comunidad — privacidad de detalle de actividad)

Revision ID: d1e2f3a4b5c7
Revises: c9d8e7f6a5b4
Create Date: 2026-07-19
"""
from alembic import op
import sqlalchemy as sa

revision = 'd1e2f3a4b5c7'
down_revision = 'c9d8e7f6a5b4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('community_share_prefs', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('community_share_prefs')
