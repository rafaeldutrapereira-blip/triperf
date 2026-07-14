"""add sport and place to personal_records

Revision ID: 5d4fb1801f71
Revises: 1c23b7fdb8c7
Create Date: 2026-07-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5d4fb1801f71'
down_revision: Union[str, Sequence[str], None] = '1c23b7fdb8c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    El formulario de Records en athlete_profile.html siempre mandó sport y
    place, pero el modelo PersonalRecord nunca tuvo esas columnas — el
    POST /athlete/personal-records fallaba 422 en todos los casos
    ("Error guardando record" genérico en el frontend).
    """
    with op.batch_alter_table('personal_records') as batch_op:
        batch_op.add_column(sa.Column('sport', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('place', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('personal_records') as batch_op:
        batch_op.drop_column('place')
        batch_op.drop_column('sport')
