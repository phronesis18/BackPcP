"""Create demande and document tables

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-07-12 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c2d3e4f5a6b7"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "demande",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("prenom", sa.String(length=100), nullable=False),
        sa.Column("nom", sa.String(length=100), nullable=False),
        sa.Column("date_naissance", sa.Date(), nullable=True),
        sa.Column("lieu_naissance", sa.String(length=100), nullable=True),
        sa.Column("cni_number", sa.String(length=50), nullable=True),
        sa.Column("situation_matrimoniale", sa.String(length=20), nullable=True),
        sa.Column("profession", sa.String(length=120), nullable=True),
        sa.Column("employeur", sa.String(length=120), nullable=True),
        sa.Column("revenu_mensuel", sa.Integer(), nullable=True),
        sa.Column("anciennete_annees", sa.Integer(), nullable=True),
        sa.Column("adresse", sa.String(length=255), nullable=True),
        sa.Column("marque", sa.String(length=50), nullable=True),
        sa.Column("modele", sa.String(length=50), nullable=True),
        sa.Column("annee", sa.Integer(), nullable=True),
        sa.Column("kilometrage", sa.Integer(), nullable=True),
        sa.Column("vendeur", sa.String(length=120), nullable=True),
        sa.Column("prix_vehicule", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duree_mois", sa.Integer(), nullable=False, server_default="48"),
        sa.Column("mensualite", sa.Integer(), nullable=True),
        sa.Column("taux_teg", sa.Float(), nullable=True, server_default="22.0"),
        sa.Column("statut", sa.String(length=20), nullable=False, server_default="soumise"),
        sa.Column(
            "owner_id",
            sa.UUID(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["user.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_demande_owner_id", "demande", ["owner_id"])

    op.create_table(
        "document",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("type", sa.String(length=120), nullable=False),
        sa.Column("nom", sa.String(length=255), nullable=True),
        sa.Column(
            "statut",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("ocr", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "demande_id",
            sa.UUID(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["demande_id"], ["demande.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_demande_id", "document", ["demande_id"])


def downgrade():
    op.drop_index("ix_document_demande_id", table_name="document")
    op.drop_table("document")
    op.drop_index("ix_demande_owner_id", table_name="demande")
    op.drop_table("demande")
