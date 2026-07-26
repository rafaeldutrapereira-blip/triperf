"""fix group_members: migrar user_id (legacy, NOT NULL) -> athlete_id

El modelo GroupMember.athlete_id existía en el código hace tiempo, pero la
tabla real nunca terminó de migrarse: 'user_id' seguía siendo la columna
NOT NULL con los datos reales, y 'athlete_id' quedó como columna nueva
vacía (nullable). Cualquier INSERT hecho por el ORM (que solo conoce
athlete_id) fallaba con "NOT NULL constraint failed: group_members.user_id".
Además toda lectura vía GroupMember.athlete_id devolvía NULL para los
registros reales, dejando "atletas de mi grupo" silenciosamente vacío.

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-07-26
"""
from alembic import op
import sqlalchemy as sa

revision = 'c2d3e4f5a6b7'
down_revision = 'b1c2d3e4f5a6'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text(
        "UPDATE group_members SET athlete_id = user_id "
        "WHERE athlete_id IS NULL AND user_id IS NOT NULL"
    ))
    with op.batch_alter_table('group_members') as batch_op:
        batch_op.alter_column('athlete_id', existing_type=sa.String(), nullable=False)
        batch_op.drop_column('user_id')


def downgrade():
    with op.batch_alter_table('group_members') as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.String(), nullable=True))
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE group_members SET user_id = athlete_id"))
    with op.batch_alter_table('group_members') as batch_op:
        batch_op.alter_column('user_id', existing_type=sa.String(), nullable=False)
        batch_op.alter_column('athlete_id', existing_type=sa.String(), nullable=True)
