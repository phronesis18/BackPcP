"""Add file storage columns to document table

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-07-12 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d3e4f5a6b7c8"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "document",
        sa.Column("content_type", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "document",
        sa.Column("fichier", sa.LargeBinary(), nullable=True),
    )


def downgrade():
    op.drop_column("document", "fichier")
    op.drop_column("document", "content_type")
