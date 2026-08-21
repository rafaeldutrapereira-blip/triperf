"""add provider column (Sprint 48 — multi-brand wearables)

Agrega la columna `provider` (default 'garmin') a las tablas de datos de
wearable, y backfillea 'strava' donde activity_id empieza con 'strava_'
(hoy es la única forma de distinguir origen — ver
docs/plan-multi-brand-wearables.md).

Revision ID: k7l8m9n0o1p2
Revises: j1k2l3m4n5o6
Create Date: 2026-08-20
"""
from alembic import op
import sqlalchemy as sa

revision = 'k7l8m9n0o1p2'
down_revision = 'j1k2l3m4n5o6'
branch_labels = None
depends_on = None

_TABLES = [
    "garmin_activities",
    "garmin_training_load",
    "garmin_sync_status",
    "garmin_health_daily",
    "garmin_sleep_sessions",
]


def upgrade():
    for table in _TABLES:
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(
                sa.Column("provider", sa.String(), nullable=False, server_default="garmin")
            )

    # Backfill: las filas de Strava ya sincronizadas se distinguen hoy solo
    # por el prefijo "strava_" en activity_id (garmin_training_load/health/
    # sleep no tienen activity_id — quedan en 'garmin' por default, que es
    # correcto porque hoy solo Garmin alimenta esas tablas).
    op.execute(
        "UPDATE garmin_activities SET provider = 'strava' "
        "WHERE activity_id LIKE 'strava_%'"
    )


def downgrade():
    for table in _TABLES:
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_column("provider")
