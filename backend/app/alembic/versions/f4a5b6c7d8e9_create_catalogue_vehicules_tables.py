"""Create catalogue vehicules tables (marque, modele, modele_annee)

Revision ID: f4a5b6c7d8e9
Revises: bbed4f7fec69
Create Date: 2026-09-05 21:00:00.000000

"""
import uuid

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f4a5b6c7d8e9"
down_revision = "bbed4f7fec69"
branch_labels = None
depends_on = None


SEED_MARQUES = [
    "Toyota",
    "Hyundai",
    "Kia",
    "Suzuki",
    "Renault",
    "Nissan",
    "Honda",
]


def upgrade():
    op.create_table(
        "marque",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("nom", sa.String(length=80), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_marque_nom", "marque", ["nom"], unique=True)

    op.create_table(
        "modele",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("nom", sa.String(length=80), nullable=False),
        sa.Column("marque_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["marque_id"], ["marque.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_modele_marque_id", "modele", ["marque_id"])

    op.create_table(
        "modele_annee",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("annee", sa.Integer(), nullable=False),
        sa.Column("kilometrage_min", sa.Integer(), nullable=True),
        sa.Column("kilometrage_max", sa.Integer(), nullable=True),
        sa.Column("modele_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["modele_id"], ["modele.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_modele_annee_modele_id", "modele_annee", ["modele_id"])

    marque_table = sa.table(
        "marque",
        sa.column("id", sa.UUID()),
        sa.column("nom", sa.String()),
    )
    op.bulk_insert(
        marque_table,
        [{"id": uuid.uuid4(), "nom": nom} for nom in SEED_MARQUES],
    )


def downgrade():
    op.drop_index("ix_modele_annee_modele_id", table_name="modele_annee")
    op.drop_table("modele_annee")
    op.drop_index("ix_modele_marque_id", table_name="modele")
    op.drop_table("modele")
    op.drop_index("ix_marque_nom", table_name="marque")
    op.drop_table("marque")
