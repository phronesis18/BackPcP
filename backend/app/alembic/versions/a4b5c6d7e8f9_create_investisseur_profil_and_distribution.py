"""Create investisseur_profil and distribution tables (dashboard investisseur)

Revision ID: a4b5c6d7e8f9
Revises: f2a3b4c5d6e7
Create Date: 2026-09-11 17:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a4b5c6d7e8f9"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "investisseur_profil",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("montant_investi", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("date_investissement", sa.Date(), nullable=True),
        sa.Column("investisseur_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["investisseur_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("investisseur_id"),
    )

    op.create_table(
        "investisseur_distribution",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("date_distribution", sa.Date(), nullable=False),
        sa.Column("montant", sa.Integer(), nullable=False),
        sa.Column("statut", sa.String(length=10), nullable=False, server_default="prevu"),
        sa.Column("investisseur_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["investisseur_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_investisseur_distribution_investisseur_id",
        "investisseur_distribution",
        ["investisseur_id"],
    )


def downgrade():
    op.drop_index(
        "ix_investisseur_distribution_investisseur_id",
        table_name="investisseur_distribution",
    )
    op.drop_table("investisseur_distribution")
    op.drop_table("investisseur_profil")
