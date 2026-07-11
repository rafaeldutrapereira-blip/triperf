"""sprint1_health_ai — Garmin health data + AI engine tables + GarminTrainingLoad ACWR

Revision ID: a1b2c3d4e5f6
Revises: ca391f8bf2e6
Create Date: 2026-06-27

Añade:
  - garmin_health_daily   (HRV, Body Battery, sleep summary, stress, SpO2, Readiness)
  - garmin_sleep_sessions (fases de sueño detalladas)
  - ai_sessions           (sesiones de chat persistidas)
  - ai_messages           (mensajes individuales con context snapshot)
  - ai_insights           (insights proactivos automáticos)
  - ai_athlete_context    (snapshot diario de contexto para el prompt)
  - Columnas nuevas en garmin_training_load: acwr, monotony, strain
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'ca391f8bf2e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── garmin_health_daily ──────────────────────────────────────────────────
    op.create_table(
        'garmin_health_daily',
        sa.Column('id',       sa.String(), nullable=False),
        sa.Column('user_id',  sa.String(), nullable=False),
        sa.Column('date_iso', sa.String(), nullable=False),
        # Body Battery
        sa.Column('body_battery_min', sa.Integer(), nullable=True),
        sa.Column('body_battery_max', sa.Integer(), nullable=True),
        sa.Column('body_battery_end', sa.Integer(), nullable=True),
        # HRV
        sa.Column('hrv_weekly_avg',    sa.Float(), nullable=True),
        sa.Column('hrv_last_night',    sa.Float(), nullable=True),
        sa.Column('hrv_baseline_low',  sa.Float(), nullable=True),
        sa.Column('hrv_baseline_high', sa.Float(), nullable=True),
        sa.Column('hrv_status',        sa.String(), nullable=True),
        # Estrés
        sa.Column('avg_stress',      sa.Integer(), nullable=True),
        sa.Column('rest_stress_pct', sa.Float(),   nullable=True),
        # Respiración y SpO2
        sa.Column('avg_respiration', sa.Float(), nullable=True),
        sa.Column('avg_spo2',        sa.Float(), nullable=True),
        sa.Column('min_spo2',        sa.Float(), nullable=True),
        # Movimiento y FC
        sa.Column('steps',           sa.Integer(), nullable=True),
        sa.Column('active_calories', sa.Integer(), nullable=True),
        sa.Column('resting_hr',      sa.Integer(), nullable=True),
        # Training Readiness
        sa.Column('training_readiness', sa.Integer(), nullable=True),
        sa.Column('recovery_time_h',    sa.Integer(), nullable=True),
        # LabX Readiness (calculado localmente)
        sa.Column('labx_readiness_score',   sa.Integer(), nullable=True),
        sa.Column('labx_readiness_factors', sa.Text(),    nullable=True),
        # Timestamps
        sa.Column('synced_at',  sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'date_iso', name='uq_health_daily'),
    )
    op.create_index('ix_health_user_date', 'garmin_health_daily', ['user_id', 'date_iso'])

    # ── garmin_sleep_sessions ────────────────────────────────────────────────
    op.create_table(
        'garmin_sleep_sessions',
        sa.Column('id',       sa.String(), nullable=False),
        sa.Column('user_id',  sa.String(), nullable=False),
        sa.Column('date_iso', sa.String(), nullable=False),
        sa.Column('sleep_start', sa.DateTime(), nullable=True),
        sa.Column('sleep_end',   sa.DateTime(), nullable=True),
        sa.Column('total_min',   sa.Integer(), nullable=True),
        sa.Column('deep_min',    sa.Integer(), nullable=True),
        sa.Column('light_min',   sa.Integer(), nullable=True),
        sa.Column('rem_min',     sa.Integer(), nullable=True),
        sa.Column('awake_min',   sa.Integer(), nullable=True),
        sa.Column('sleep_score',      sa.Integer(), nullable=True),
        sa.Column('sleep_score_qual', sa.String(),  nullable=True),
        sa.Column('avg_spo2_night',         sa.Float(), nullable=True),
        sa.Column('avg_respiration_night',   sa.Float(), nullable=True),
        sa.Column('hrv_rmssd_night',         sa.Float(), nullable=True),
        sa.Column('raw_stages_json', sa.Text(), nullable=True),
        sa.Column('synced_at',  sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'date_iso', name='uq_sleep_session'),
    )
    op.create_index('ix_sleep_user_date', 'garmin_sleep_sessions', ['user_id', 'date_iso'])

    # ── ai_sessions ──────────────────────────────────────────────────────────
    op.create_table(
        'ai_sessions',
        sa.Column('id',              sa.String(), nullable=False),
        sa.Column('user_id',         sa.String(), nullable=False),
        sa.Column('title',           sa.String(), nullable=True),
        sa.Column('last_message_at', sa.DateTime(), nullable=True),
        sa.Column('deleted_at',      sa.DateTime(), nullable=True),
        sa.Column('created_at',      sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_ai_session_user', 'ai_sessions', ['user_id', 'last_message_at'])

    # ── ai_messages ──────────────────────────────────────────────────────────
    op.create_table(
        'ai_messages',
        sa.Column('id',               sa.String(), nullable=False),
        sa.Column('session_id',       sa.String(), nullable=False),
        sa.Column('role',             sa.String(), nullable=False),
        sa.Column('content',          sa.Text(),   nullable=False),
        sa.Column('context_snapshot', sa.Text(),   nullable=True),
        sa.Column('tokens_input',     sa.Integer(), nullable=True),
        sa.Column('tokens_output',    sa.Integer(), nullable=True),
        sa.Column('model_version',    sa.String(),  nullable=True),
        sa.Column('created_at',       sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['session_id'], ['ai_sessions.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_ai_messages_session_id'), 'ai_messages', ['session_id'])

    # ── ai_insights ──────────────────────────────────────────────────────────
    op.create_table(
        'ai_insights',
        sa.Column('id',              sa.String(), nullable=False),
        sa.Column('user_id',         sa.String(), nullable=False),
        sa.Column('type',            sa.String(), nullable=False),
        sa.Column('severity',        sa.String(), nullable=True),
        sa.Column('title',           sa.String(), nullable=False),
        sa.Column('body',            sa.Text(),   nullable=False),
        sa.Column('cta_text',        sa.String(), nullable=True),
        sa.Column('cta_url',         sa.String(), nullable=True),
        sa.Column('data_snapshot',   sa.Text(),   nullable=True),
        sa.Column('acknowledged_at', sa.DateTime(), nullable=True),
        sa.Column('dismissed_at',    sa.DateTime(), nullable=True),
        sa.Column('expires_at',      sa.DateTime(), nullable=True),
        sa.Column('created_at',      sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_insight_user_active', 'ai_insights', ['user_id', 'created_at'])

    # ── ai_athlete_context ───────────────────────────────────────────────────
    op.create_table(
        'ai_athlete_context',
        sa.Column('user_id',           sa.String(), nullable=False),
        sa.Column('context_json',      sa.Text(),    nullable=True),
        sa.Column('current_ctl',       sa.Float(),   nullable=True),
        sa.Column('current_atl',       sa.Float(),   nullable=True),
        sa.Column('current_tsb',       sa.Float(),   nullable=True),
        sa.Column('current_acwr',      sa.Float(),   nullable=True),
        sa.Column('current_hrv',       sa.Float(),   nullable=True),
        sa.Column('current_readiness', sa.Integer(), nullable=True),
        sa.Column('injury_risk_score', sa.Float(),   nullable=True),
        sa.Column('days_to_race',      sa.Integer(), nullable=True),
        sa.Column('context_built_at',  sa.DateTime(), nullable=True),
        sa.Column('updated_at',        sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('user_id'),
        sa.UniqueConstraint('user_id', name='uq_ai_context_user'),
    )

    # ── Nuevas columnas en garmin_training_load ──────────────────────────────
    op.add_column('garmin_training_load',
        sa.Column('acwr',     sa.Float(), nullable=True))
    op.add_column('garmin_training_load',
        sa.Column('monotony', sa.Float(), nullable=True))
    op.add_column('garmin_training_load',
        sa.Column('strain',   sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('garmin_training_load', 'strain')
    op.drop_column('garmin_training_load', 'monotony')
    op.drop_column('garmin_training_load', 'acwr')

    op.drop_table('ai_athlete_context')
    op.drop_index('ix_insight_user_active', table_name='ai_insights')
    op.drop_table('ai_insights')
    op.drop_index(op.f('ix_ai_messages_session_id'), table_name='ai_messages')
    op.drop_table('ai_messages')
    op.drop_index('ix_ai_session_user', table_name='ai_sessions')
    op.drop_table('ai_sessions')
    op.drop_index('ix_sleep_user_date', table_name='garmin_sleep_sessions')
    op.drop_table('garmin_sleep_sessions')
    op.drop_index('ix_health_user_date', table_name='garmin_health_daily')
    op.drop_table('garmin_health_daily')
