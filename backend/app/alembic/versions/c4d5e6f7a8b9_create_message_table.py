"""Create message table (chat)

Revision ID: c4d5e6f7a8b9
Revises: 9d0b65317871
Create Date: 2026-09-06 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c4d5e6f7a8b9"
down_revision = "9d0b65317871"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "message",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("contenu", sa.String(length=2000), nullable=False),
        sa.Column("demande_id", sa.UUID(), nullable=False),
        sa.Column("sender_id", sa.UUID(), nullable=False),
        sa.Column("sender_role", sa.String(length=10), nullable=False),
        sa.Column("lu_par_client", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("lu_par_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["demande_id"], ["demande.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_message_demande_id", "message", ["demande_id"])


def downgrade():
    op.drop_index("ix_message_demande_id", table_name="message")
    op.drop_table("message")
