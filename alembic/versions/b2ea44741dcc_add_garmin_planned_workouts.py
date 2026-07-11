"""add garmin_planned_workouts

Revision ID: b2ea44741dcc
Revises: f3a4b5c6d7e8
Create Date: 2026-07-08 21:14:48.782253

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'b2ea44741dcc'
down_revision: Union[str, Sequence[str], None] = 'f3a4b5c6d7e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'garmin_planned_workouts',
        sa.Column('id',                  sa.String(),  primary_key=True),
        sa.Column('user_id',             sa.String(),  nullable=False),
        sa.Column('date_iso',            sa.String(),  nullable=False),
        sa.Column('garmin_scheduled_id', sa.String(),  nullable=True),
        sa.Column('title',               sa.String(),  nullable=True),
        sa.Column('sport',               sa.String(),  nullable=True),
        sa.Column('dur_min',             sa.Float(),   nullable=True),
        sa.Column('dist_km',             sa.Float(),   nullable=True),
        sa.Column('tss_planned',         sa.Float(),   nullable=True),
        sa.Column('source',              sa.String(),  nullable=True),
        sa.Column('raw_json',            sa.Text(),    nullable=True),
    )
    op.create_index('ix_gpw_user_date', 'garmin_planned_workouts', ['user_id', 'date_iso'])


def downgrade() -> None:
    op.drop_index('ix_gpw_user_date', table_name='garmin_planned_workouts')
    op.drop_table('garmin_planned_workouts')
