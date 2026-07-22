"""add users.avatar_photo_path (foto de perfil real, en vez de solo iniciales)

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-21
"""
from alembic import op
import sqlalchemy as sa

revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('avatar_photo_path', sa.String(), nullable=True))


def downgrade():
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('avatar_photo_path')
