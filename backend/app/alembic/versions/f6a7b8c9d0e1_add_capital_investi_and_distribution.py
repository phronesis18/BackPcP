"""Add capital_investi to User and create distribution table

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-09-10 09:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("user", sa.Column("capital_investi", sa.Integer(), nullable=True))

    op.create_table(
        "distribution",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("periode", sa.String(length=40), nullable=False),
        sa.Column("montant_total", sa.Integer(), nullable=False),
        sa.Column(
            "statut",
            sa.Enum("prevue", "versee", name="statutdistribution"),
            nullable=False,
            server_default="prevue",
        ),
        sa.Column("date_versement", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("distribution")
    sa.Enum(name="statutdistribution").drop(op.get_bind(), checkfirst=True)
    op.drop_column("user", "capital_investi")
