"""add gear management module (running shoes + bikes + components)

Modulo "Gestion de Equipamiento y Mantenimiento" -- ver artifact de diseno
publicado 2026-08-22 (memoria project-labx-gear-module-design). 6 tablas
nuevas: running_shoes, shoe_activity_links, bikes, bike_components,
bike_activity_links, maintenance_logs.

Revision ID: m9n0o1p2q3r4
Revises: l8m9n0o1p2q3
Create Date: 2026-08-22
"""
from alembic import op
import sqlalchemy as sa

revision = 'm9n0o1p2q3r4'
down_revision = 'l8m9n0o1p2q3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'running_shoes',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('brand', sa.String(), nullable=False),
        sa.Column('model', sa.String(), nullable=False),
        sa.Column('nickname', sa.String(), nullable=True),
        sa.Column('purchase_date', sa.Date(), nullable=True),
        sa.Column('shoe_type', sa.String(), nullable=False, server_default='rodaje'),
        sa.Column('target_km', sa.Float(), nullable=False, server_default='700.0'),
        sa.Column('accumulated_km', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('status', sa.String(), nullable=False, server_default='active'),
        sa.Column('default_for_json', sa.Text(), nullable=True),
        sa.Column('last_alert_pct', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_shoes_user', 'running_shoes', ['user_id'])

    op.create_table(
        'shoe_activity_links',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('shoe_id', sa.String(), sa.ForeignKey('running_shoes.id'), nullable=False),
        sa.Column('activity_id', sa.String(), sa.ForeignKey('garmin_activities.id'), nullable=False),
        sa.Column('distance_km', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('activity_id', name='uq_shoe_activity'),
    )
    op.create_index('ix_sal_shoe', 'shoe_activity_links', ['shoe_id'])

    op.create_table(
        'bikes',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('brand', sa.String(), nullable=False),
        sa.Column('model', sa.String(), nullable=False),
        sa.Column('bike_type', sa.String(), nullable=False, server_default='ruta'),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('status', sa.String(), nullable=False, server_default='active'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_bikes_user', 'bikes', ['user_id'])

    op.create_table(
        'bike_components',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('bike_id', sa.String(), sa.ForeignKey('bikes.id'), nullable=False),
        sa.Column('component_type', sa.String(), nullable=False),
        sa.Column('label', sa.String(), nullable=True),
        sa.Column('tracking_unit', sa.String(), nullable=False, server_default='km'),
        sa.Column('target_value', sa.Float(), nullable=False),
        sa.Column('accumulated_value', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('charge_pct', sa.Integer(), nullable=True),
        sa.Column('installed_date', sa.Date(), nullable=True),
        sa.Column('last_service_date', sa.Date(), nullable=True),
        sa.Column('last_alert_pct', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='active'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_components_bike', 'bike_components', ['bike_id'])

    op.create_table(
        'bike_activity_links',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('bike_id', sa.String(), sa.ForeignKey('bikes.id'), nullable=False),
        sa.Column('activity_id', sa.String(), sa.ForeignKey('garmin_activities.id'), nullable=False),
        sa.Column('distance_km', sa.Float(), nullable=False),
        sa.Column('duration_s', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('activity_id', name='uq_bike_activity'),
    )
    op.create_index('ix_bal_bike', 'bike_activity_links', ['bike_id'])

    op.create_table(
        'maintenance_logs',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('bike_id', sa.String(), sa.ForeignKey('bikes.id'), nullable=False),
        sa.Column('component_id', sa.String(), sa.ForeignKey('bike_components.id'), nullable=True),
        sa.Column('date_iso', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('cost', sa.Float(), nullable=True),
        sa.Column('resets_accumulated', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_maint_bike', 'maintenance_logs', ['bike_id'])


def downgrade():
    op.drop_table('maintenance_logs')
    op.drop_table('bike_activity_links')
    op.drop_table('bike_components')
    op.drop_table('bikes')
    op.drop_table('shoe_activity_links')
    op.drop_table('running_shoes')
