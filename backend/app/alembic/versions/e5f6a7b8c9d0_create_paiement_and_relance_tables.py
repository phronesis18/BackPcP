"""Create paiement and relance tables (Recover Bot)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-10 09:05:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "paiement",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("contrat_id", sa.UUID(), nullable=False),
        sa.Column("index", sa.Integer(), nullable=False),
        sa.Column("date_echeance", sa.Date(), nullable=False),
        sa.Column("montant", sa.Integer(), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mode_paiement", sa.String(length=30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["contrat_id"], ["contrat.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("contrat_id", "index"),
    )
    op.create_index("ix_paiement_contrat_id", "paiement", ["contrat_id"])

    op.create_table(
        "relance",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("contrat_id", sa.UUID(), nullable=False),
        sa.Column(
            "canal",
            sa.Enum("sms", "whatsapp", "appel", "coupe_moteur", "reactivation", name="canalrelance"),
            nullable=False,
        ),
        sa.Column(
            "origine",
            sa.Enum("auto", "manuel", name="originerelance"),
            nullable=False,
            server_default="auto",
        ),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["contrat_id"], ["contrat.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_relance_contrat_id", "relance", ["contrat_id"])


def downgrade():
    op.drop_index("ix_relance_contrat_id", table_name="relance")
    op.drop_table("relance")
    sa.Enum(name="canalrelance").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="originerelance").drop(op.get_bind(), checkfirst=True)

    op.drop_index("ix_paiement_contrat_id", table_name="paiement")
    op.drop_table("paiement")
