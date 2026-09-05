"""Create vendeur table

Revision ID: a7b8c9d0e1f2
Revises: f4a5b6c7d8e9
Create Date: 2026-09-05 22:00:00.000000

"""
import uuid

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a7b8c9d0e1f2"
down_revision = "f4a5b6c7d8e9"
branch_labels = None
depends_on = None


SEED_VENDEURS = [
    "CFAO Motors Bénin",
    "SDA Bénin",
    "Vendeur particulier",
]


def upgrade():
    op.create_table(
        "vendeur",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("nom", sa.String(length=120), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vendeur_nom", "vendeur", ["nom"], unique=True)

    vendeur_table = sa.table(
        "vendeur",
        sa.column("id", sa.UUID()),
        sa.column("nom", sa.String()),
    )
    op.bulk_insert(
        vendeur_table,
        [{"id": uuid.uuid4(), "nom": nom} for nom in SEED_VENDEURS],
    )


def downgrade():
    op.drop_index("ix_vendeur_nom", table_name="vendeur")
    op.drop_table("vendeur")
