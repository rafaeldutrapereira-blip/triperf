"""merge de las tres cabezas de Alembic

Hay tres ramas sin unir en el historial de migraciones:
  - d4e5f6a7b8c9: garmin_push_status/error/at en assigned_workouts
  - f3a4b5c6d7e8: users.age
  - o1p2q3r4s5t6: users.lang

Esta migración no cambia el esquema: solo une las tres ramas en una única
cabeza. Las columnas de cada rama las siguen creando sus propias migraciones.

Revision ID: b8e2c4d6f1a9
Revises: d4e5f6a7b8c9, f3a4b5c6d7e8, o1p2q3r4s5t6
Create Date: 2026-10-18
"""
from alembic import op
import sqlalchemy as sa  # noqa: F401


revision = 'b8e2c4d6f1a9'
down_revision = ('d4e5f6a7b8c9', 'f3a4b5c6d7e8', 'o1p2q3r4s5t6')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
