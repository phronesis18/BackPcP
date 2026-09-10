"""Create echeance and actionrecouvrement tables (recouvrement module)

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-09-11 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f7a8b9c0d1e2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "echeance",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("demande_id", sa.UUID(), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("date_echeance", sa.Date(), nullable=False),
        sa.Column("montant", sa.Integer(), nullable=False),
        sa.Column("payee", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("payee_le", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["demande_id"], ["demande.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_echeance_demande_id", "echeance", ["demande_id"])

    op.create_table(
        "actionrecouvrement",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("type", sa.String(length=30), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("demande_id", sa.UUID(), nullable=False),
        sa.Column("created_by_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["demande_id"], ["demande.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_actionrecouvrement_demande_id", "actionrecouvrement", ["demande_id"]
    )


def downgrade():
    op.drop_index("ix_actionrecouvrement_demande_id", table_name="actionrecouvrement")
    op.drop_table("actionrecouvrement")
    op.drop_index("ix_echeance_demande_id", table_name="echeance")
    op.drop_table("echeance")
