"""Add ocr_resultat JSON column to document

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-12 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("document", sa.Column("ocr_resultat", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("document", "ocr_resultat")
