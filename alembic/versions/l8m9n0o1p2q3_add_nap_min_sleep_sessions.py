"""add nap_min to garmin_sleep_sessions (siestas, separadas del sueno nocturno)

Verificado con datos reales del propio cache de sync (data/cache/sleep_*.json):
garminconnect.get_sleep_data() SI trae dailySleepDTO.napTimeSeconds -- 35 dias
reales con valor != 0 en la cuenta del usuario, rango 18-108 min. Se guarda
como columna hermana de total_min, NUNCA sumada a el (una siesta corta no
tiene la misma arquitectura de sueno que el descanso nocturno -- sumarla
distorsionaria el sleep_score). Ver docs/plan-multi-brand-wearables.md.

Revision ID: l8m9n0o1p2q3
Revises: k7l8m9n0o1p2
Create Date: 2026-08-22
"""
from alembic import op
import sqlalchemy as sa

revision = 'l8m9n0o1p2q3'
down_revision = 'k7l8m9n0o1p2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('garmin_sleep_sessions') as batch_op:
        batch_op.add_column(sa.Column('nap_min', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('garmin_sleep_sessions') as batch_op:
        batch_op.drop_column('nap_min')
