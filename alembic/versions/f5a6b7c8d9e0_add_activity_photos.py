"""add activity_photos table (galería de fotos manuales por actividad)

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-07-29
"""
from alembic import op
import sqlalchemy as sa

revision = 'f5a6b7c8d9e0'
down_revision = 'e4f5a6b7c8d9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'activity_photos',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('activity_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('storage_key', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['activity_id'], ['garmin_activities.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_activity_photos_activity', 'activity_photos', ['activity_id'])


def downgrade():
    op.drop_index('ix_activity_photos_activity', table_name='activity_photos')
    op.drop_table('activity_photos')
