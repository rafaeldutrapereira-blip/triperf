"""wellness_log 6-factor columns (energy, motivation, stress, sleep_quality)

Revision ID: 73420eb748d0
Revises: 5d4fb1801f71
Create Date: 2026-07-16
"""
from alembic import op
import sqlalchemy as sa

revision = '73420eb748d0'
down_revision = '5d4fb1801f71'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('wellness_logs') as batch_op:
        batch_op.add_column(sa.Column('energy', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('motivation', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('stress', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('sleep_quality', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('wellness_logs') as batch_op:
        batch_op.drop_column('sleep_quality')
        batch_op.drop_column('stress')
        batch_op.drop_column('motivation')
        batch_op.drop_column('energy')
