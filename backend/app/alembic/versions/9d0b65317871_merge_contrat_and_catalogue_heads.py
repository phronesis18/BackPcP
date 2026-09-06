"""Merge contrat and catalogue/parametres heads

Revision ID: 9d0b65317871
Revises: f1a2b3c4d5e6, b3c4d5e6f7a8
Create Date: 2026-09-06 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9d0b65317871"
down_revision = ("f1a2b3c4d5e6", "b3c4d5e6f7a8")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
