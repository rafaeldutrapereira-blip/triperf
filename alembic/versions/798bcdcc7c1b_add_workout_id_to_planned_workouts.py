"""add_workout_id_to_planned_workouts

Revision ID: 798bcdcc7c1b
Revises: 1e9097a6ac61
Create Date: 2026-07-11 17:35:58.107277

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '798bcdcc7c1b'
down_revision: Union[str, Sequence[str], None] = '1e9097a6ac61'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('garmin_planned_workouts', sa.Column('workout_id', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('garmin_planned_workouts', 'workout_id')
