"""add training effect fields to garmin activity

Revision ID: 1ef895d22a4a
Revises: d4e5f6a7b8c9
Create Date: 2026-07-31 20:48:56.493083

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1ef895d22a4a'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("garmin_activities") as batch_op:
        batch_op.add_column(sa.Column("aerobic_te", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("anaerobic_te", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("te_label", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("garmin_activities") as batch_op:
        batch_op.drop_column("te_label")
        batch_op.drop_column("anaerobic_te")
        batch_op.drop_column("aerobic_te")
