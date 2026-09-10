"""Add seuil_scoring_auto, montant_min, montant_max to parametresfinanciers

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-09-10 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "parametresfinanciers",
        sa.Column("seuil_scoring_auto", sa.Integer(), nullable=False, server_default="650"),
    )
    op.add_column(
        "parametresfinanciers",
        sa.Column("montant_min", sa.Integer(), nullable=False, server_default="1000000"),
    )
    op.add_column(
        "parametresfinanciers",
        sa.Column("montant_max", sa.Integer(), nullable=False, server_default="30000000"),
    )


def downgrade():
    op.drop_column("parametresfinanciers", "montant_max")
    op.drop_column("parametresfinanciers", "montant_min")
    op.drop_column("parametresfinanciers", "seuil_scoring_auto")
