"""add all missing user columns: strava, gdpr, notifications

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a4
Create Date: 2026-07-04

Migración quirúrgica — agrega columnas de Strava, GDPR y notificaciones
que existen en models.py pero no en el DB. Idempotente via _column_exists().
"""
from alembic import op
import sqlalchemy as sa


revision = 'c0d1e2f3a4b5'
down_revision = 'b9c0d1e2f3a4'
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    cols = [row[1] for row in conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()]
    return column in cols


def upgrade() -> None:
    # Strava OAuth columns
    if not _column_exists("users", "strava_athlete_id"):
        op.add_column("users", sa.Column("strava_athlete_id", sa.String(), nullable=True))
    if not _column_exists("users", "strava_access_token"):
        op.add_column("users", sa.Column("strava_access_token", sa.Text(), nullable=True))
    if not _column_exists("users", "strava_refresh_token"):
        op.add_column("users", sa.Column("strava_refresh_token", sa.Text(), nullable=True))
    if not _column_exists("users", "strava_token_expires_at"):
        op.add_column("users", sa.Column("strava_token_expires_at", sa.DateTime(), nullable=True))

    # GDPR consent columns
    if not _column_exists("users", "gdpr_consent_at"):
        op.add_column("users", sa.Column("gdpr_consent_at", sa.DateTime(), nullable=True))
    if not _column_exists("users", "gdpr_consent_ip"):
        op.add_column("users", sa.Column("gdpr_consent_ip", sa.String(), nullable=True))

    # Notification preference columns
    if not _column_exists("users", "notif_email_weekly"):
        op.add_column("users", sa.Column("notif_email_weekly", sa.Boolean(), nullable=True, server_default="1"))
    if not _column_exists("users", "notif_email_workout"):
        op.add_column("users", sa.Column("notif_email_workout", sa.Boolean(), nullable=True, server_default="1"))
    if not _column_exists("users", "notif_push_wellness"):
        op.add_column("users", sa.Column("notif_push_wellness", sa.Boolean(), nullable=True, server_default="1"))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("notif_push_wellness")
        batch_op.drop_column("notif_email_workout")
        batch_op.drop_column("notif_email_weekly")
        batch_op.drop_column("gdpr_consent_ip")
        batch_op.drop_column("gdpr_consent_at")
        batch_op.drop_column("strava_token_expires_at")
        batch_op.drop_column("strava_refresh_token")
        batch_op.drop_column("strava_access_token")
        batch_op.drop_column("strava_athlete_id")
