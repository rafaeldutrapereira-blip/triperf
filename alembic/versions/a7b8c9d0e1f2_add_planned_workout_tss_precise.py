"""add garmin_planned_workouts.tss_planned_precise (Nivel 1 real vs Nivel 2 aproximado)

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-07-27
"""
from alembic import op
import sqlalchemy as sa

revision = 'a7b8c9d0e1f2'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('garmin_planned_workouts') as batch_op:
        batch_op.add_column(sa.Column('tss_planned_precise', sa.Boolean(), nullable=True))


def downgrade():
    with op.batch_alter_table('garmin_planned_workouts') as batch_op:
        batch_op.drop_column('tss_planned_precise')
