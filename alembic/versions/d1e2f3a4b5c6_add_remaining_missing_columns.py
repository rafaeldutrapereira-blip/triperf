"""add remaining missing columns across 8 tables

Revision ID: d1e2f3a4b5c6
Revises: c0d1e2f3a4b5
Create Date: 2026-07-04

Migración quirúrgica — agrega columnas detectadas por audit completo model/DB.
Idempotente via _column_exists().
"""
from alembic import op
import sqlalchemy as sa


revision = 'd1e2f3a4b5c6'
down_revision = 'c0d1e2f3a4b5'
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    cols = [row[1] for row in conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()]
    return column in cols


def upgrade() -> None:
    # assigned_workouts
    if not _column_exists("assigned_workouts", "deleted_at"):
        op.add_column("assigned_workouts", sa.Column("deleted_at", sa.DateTime(), nullable=True))

    # blood_lab_exams
    if not _column_exists("blood_lab_exams", "notes"):
        op.add_column("blood_lab_exams", sa.Column("notes", sa.Text(), nullable=True))
    if not _column_exists("blood_lab_exams", "ai_interpretation"):
        op.add_column("blood_lab_exams", sa.Column("ai_interpretation", sa.Text(), nullable=True))
    if not _column_exists("blood_lab_exams", "ai_interpreted_at"):
        op.add_column("blood_lab_exams", sa.Column("ai_interpreted_at", sa.DateTime(), nullable=True))

    # garmin_activities
    if not _column_exists("garmin_activities", "photo_path"):
        op.add_column("garmin_activities", sa.Column("photo_path", sa.String(), nullable=True))
    if not _column_exists("garmin_activities", "pool_length_m"):
        op.add_column("garmin_activities", sa.Column("pool_length_m", sa.Integer(), nullable=True))
    if not _column_exists("garmin_activities", "swolf"):
        op.add_column("garmin_activities", sa.Column("swolf", sa.Float(), nullable=True))
    if not _column_exists("garmin_activities", "avg_cadence_spm"):
        op.add_column("garmin_activities", sa.Column("avg_cadence_spm", sa.Float(), nullable=True))

    # garmin_training_load
    if not _column_exists("garmin_training_load", "monotony"):
        op.add_column("garmin_training_load", sa.Column("monotony", sa.Float(), nullable=True))
    if not _column_exists("garmin_training_load", "acwr"):
        op.add_column("garmin_training_load", sa.Column("acwr", sa.Float(), nullable=True))
    if not _column_exists("garmin_training_load", "strain"):
        op.add_column("garmin_training_load", sa.Column("strain", sa.Float(), nullable=True))

    # groups — descripcion (nullable so existing rows unaffected)
    if not _column_exists("groups", "descripcion"):
        op.add_column("groups", sa.Column("descripcion", sa.Text(), nullable=True))

    # group_members — athlete_id (NOT NULL in model, added as nullable for existing rows)
    if not _column_exists("group_members", "athlete_id"):
        op.add_column("group_members", sa.Column("athlete_id", sa.String(), nullable=True))

    # wellness_logs
    if not _column_exists("wellness_logs", "deleted_at"):
        op.add_column("wellness_logs", sa.Column("deleted_at", sa.DateTime(), nullable=True))

    # workout_logs
    if not _column_exists("workout_logs", "deleted_at"):
        op.add_column("workout_logs", sa.Column("deleted_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    for tbl, col in [
        ("workout_logs", "deleted_at"),
        ("wellness_logs", "deleted_at"),
        ("group_members", "athlete_id"),
        ("groups", "descripcion"),
        ("garmin_training_load", "strain"),
        ("garmin_training_load", "acwr"),
        ("garmin_training_load", "monotony"),
        ("garmin_activities", "avg_cadence_spm"),
        ("garmin_activities", "swolf"),
        ("garmin_activities", "pool_length_m"),
        ("garmin_activities", "photo_path"),
        ("blood_lab_exams", "ai_interpreted_at"),
        ("blood_lab_exams", "ai_interpretation"),
        ("blood_lab_exams", "notes"),
        ("assigned_workouts", "deleted_at"),
    ]:
        with op.batch_alter_table(tbl) as batch_op:
            batch_op.drop_column(col)
