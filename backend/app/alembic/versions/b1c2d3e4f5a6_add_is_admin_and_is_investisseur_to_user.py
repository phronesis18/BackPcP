"""Add is_admin and is_investisseur to User

Revision ID: b1c2d3e4f5a6
Revises: a3b7c1d2e4f5
Create Date: 2026-07-12 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b1c2d3e4f5a6"
down_revision = "a3b7c1d2e4f5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "user",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "user",
        sa.Column(
            "is_investisseur", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )


def downgrade():
    op.drop_column("user", "is_investisseur")
    op.drop_column("user", "is_admin")
