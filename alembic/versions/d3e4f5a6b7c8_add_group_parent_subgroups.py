"""add groups.parent_group_id (subgrupos dentro de un grupo)

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-07-26
"""
from alembic import op
import sqlalchemy as sa

revision = 'd3e4f5a6b7c8'
down_revision = 'c2d3e4f5a6b7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('groups') as batch_op:
        batch_op.add_column(sa.Column('parent_group_id', sa.String(), nullable=True))
        batch_op.create_foreign_key('fk_groups_parent_group_id', 'groups', ['parent_group_id'], ['id'])


def downgrade():
    with op.batch_alter_table('groups') as batch_op:
        batch_op.drop_constraint('fk_groups_parent_group_id', type_='foreignkey')
        batch_op.drop_column('parent_group_id')
