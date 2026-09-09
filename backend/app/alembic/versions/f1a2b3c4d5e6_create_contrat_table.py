"""Create contrat table

Revision ID: f1a2b3c4d5e6
Revises: bbed4f7fec69
Create Date: 2026-09-06 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f1a2b3c4d5e6"
down_revision = "bbed4f7fec69"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "contrat",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("demande_id", sa.UUID(), nullable=False),
        sa.Column("contenu", sa.Text(), nullable=False),
        sa.Column("signature", sa.Text(), nullable=False),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["demande_id"], ["demande.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("demande_id"),
    )


def downgrade():
    op.drop_table("contrat")
