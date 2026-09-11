"""Create investisseur_message table (chat admin <-> investisseur)

Revision ID: e1f2a3b4c5d6
Revises: b2c3d4e5f6a7
Create Date: 2026-09-11 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e1f2a3b4c5d6"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "investisseur_message",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("contenu", sa.String(length=2000), nullable=False),
        sa.Column("investisseur_id", sa.UUID(), nullable=False),
        sa.Column("sender_id", sa.UUID(), nullable=False),
        sa.Column("sender_role", sa.String(length=15), nullable=False),
        sa.Column(
            "lu_par_investisseur", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("lu_par_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["investisseur_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_investisseur_message_investisseur_id",
        "investisseur_message",
        ["investisseur_id"],
    )


def downgrade():
    op.drop_index(
        "ix_investisseur_message_investisseur_id", table_name="investisseur_message"
    )
    op.drop_table("investisseur_message")
