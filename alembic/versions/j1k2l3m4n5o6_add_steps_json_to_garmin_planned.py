"""add steps_json and description to garmin_planned_workouts

Revision ID: j1k2l3m4n5o6
Revises: 1ef895d22a4a
Create Date: 2026-08-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'j1k2l3m4n5o6'
down_revision: Union[str, Sequence[str], None] = '1ef895d22a4a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("garmin_planned_workouts") as batch_op:
        batch_op.add_column(sa.Column("steps_json", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("garmin_planned_workouts") as batch_op:
        batch_op.drop_column("description")
        batch_op.drop_column("steps_json")
