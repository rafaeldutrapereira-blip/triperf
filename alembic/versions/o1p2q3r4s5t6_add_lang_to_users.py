"""add lang column to users

i18n Sprint 5: idioma preferido ("es"|"pt"|"en"), persistido server-side
para traducir emails transaccionales (bienvenida, drips, alertas) que se
generan en background sin contexto de request/localStorage del navegador.

Revision ID: o1p2q3r4s5t6
Revises: n0o1p2q3r4s5
Create Date: 2026-10-16
"""
from alembic import op
import sqlalchemy as sa

revision = 'o1p2q3r4s5t6'
down_revision = 'n0o1p2q3r4s5'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('lang', sa.String(), nullable=True, server_default='es'))


def downgrade():
    op.drop_column('users', 'lang')
