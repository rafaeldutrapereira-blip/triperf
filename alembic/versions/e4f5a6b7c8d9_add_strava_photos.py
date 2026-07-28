"""add garmin_activities.strava_photos_json (fotos auto-importadas de Strava/Zwift)

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-07-28
"""
from alembic import op
import sqlalchemy as sa

revision = 'e4f5a6b7c8d9'
down_revision = 'd3e4f5a6b7c8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('garmin_activities') as batch_op:
        batch_op.add_column(sa.Column('strava_photos_json', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('garmin_activities') as batch_op:
        batch_op.drop_column('strava_photos_json')
