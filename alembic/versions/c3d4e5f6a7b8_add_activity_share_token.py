"""add garmin_activities.share_token (link público de actividad, sin login)

Revision ID: c3d4e5f6a7b8
Revises: f5a6b7c8d9e0
Create Date: 2026-07-28
"""
from alembic import op
import sqlalchemy as sa

revision = 'c3d4e5f6a7b8'
down_revision = 'f5a6b7c8d9e0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('garmin_activities') as batch_op:
        batch_op.add_column(sa.Column('share_token', sa.String(), nullable=True))
        batch_op.create_index('ix_garmin_activities_share_token', ['share_token'], unique=True)


def downgrade():
    with op.batch_alter_table('garmin_activities') as batch_op:
        batch_op.drop_index('ix_garmin_activities_share_token')
        batch_op.drop_column('share_token')
