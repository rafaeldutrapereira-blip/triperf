"""add_vo2max_garmin_columns

Revision ID: 1e9097a6ac61
Revises: b2ea44741dcc
Create Date: 2026-07-10 21:31:27.704743

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1e9097a6ac61'
down_revision: Union[str, Sequence[str], None] = 'b2ea44741dcc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('garmin_health_daily', sa.Column('vo2max_running', sa.Float(), nullable=True))
    op.add_column('garmin_health_daily', sa.Column('vo2max_cycling', sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('garmin_health_daily', 'vo2max_cycling')
    op.drop_column('garmin_health_daily', 'vo2max_running')
