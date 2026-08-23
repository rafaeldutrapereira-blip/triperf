"""add weekday schedule + tracking start date to running_shoes

Sprint 6 del módulo de Equipamiento: permite definir qué días de la
semana se usa cada zapatilla (asignación automática por día en vez de
solo por tipo "rodaje"), y una fecha de inicio de uso para recalcular
retroactivamente el km ya corrido con ese par.

Revision ID: n0o1p2q3r4s5
Revises: m9n0o1p2q3r4
Create Date: 2026-08-23
"""
from alembic import op
import sqlalchemy as sa

revision = 'n0o1p2q3r4s5'
down_revision = 'm9n0o1p2q3r4'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('running_shoes', sa.Column('schedule_days_json', sa.Text(), nullable=True))
    op.add_column('running_shoes', sa.Column('tracking_start_date', sa.Date(), nullable=True))


def downgrade():
    op.drop_column('running_shoes', 'tracking_start_date')
    op.drop_column('running_shoes', 'schedule_days_json')
