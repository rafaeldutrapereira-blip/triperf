"""rename plan_nivel pro to agegroup

Revision ID: 1c23b7fdb8c7
Revises: 798bcdcc7c1b
Create Date: 2026-07-12 10:52:04.230693

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1c23b7fdb8c7'
down_revision: Union[str, Sequence[str], None] = '798bcdcc7c1b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Renombra el valor de plan_nivel 'pro' -> 'agegroup' (rebrand de marketing)."""
    op.execute("UPDATE users SET plan_nivel = 'agegroup' WHERE plan_nivel = 'pro'")


def downgrade() -> None:
    """Revierte 'agegroup' -> 'pro'."""
    op.execute("UPDATE users SET plan_nivel = 'pro' WHERE plan_nivel = 'agegroup'")
