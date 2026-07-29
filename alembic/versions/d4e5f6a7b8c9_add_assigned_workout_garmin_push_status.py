"""add assigned_workouts.garmin_push_status/error/at (visibilidad del push a Garmin para el coach)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-29
"""
from alembic import op
import sqlalchemy as sa

revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('assigned_workouts') as batch_op:
        batch_op.add_column(sa.Column('garmin_push_status', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('garmin_push_error', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('garmin_push_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('assigned_workouts') as batch_op:
        batch_op.drop_column('garmin_push_at')
        batch_op.drop_column('garmin_push_error')
        batch_op.drop_column('garmin_push_status')
