"""Generalize investisseur_message into a generic user_message table (admin <-> any user)

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-09-11 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade():
    op.rename_table("investisseur_message", "user_message")
    op.alter_column(
        "user_message", "investisseur_id", new_column_name="user_id", existing_type=sa.UUID()
    )
    op.alter_column(
        "user_message",
        "lu_par_investisseur",
        new_column_name="lu_par_user",
        existing_type=sa.Boolean(),
        existing_server_default=sa.false(),
    )
    op.execute("ALTER INDEX ix_investisseur_message_investisseur_id RENAME TO ix_user_message_user_id")
    op.execute("UPDATE user_message SET sender_role = 'user' WHERE sender_role = 'investisseur'")
    op.alter_column(
        "user_message", "sender_role", existing_type=sa.String(length=15), type_=sa.String(length=10)
    )


def downgrade():
    op.alter_column(
        "user_message", "sender_role", existing_type=sa.String(length=10), type_=sa.String(length=15)
    )
    op.execute("UPDATE user_message SET sender_role = 'investisseur' WHERE sender_role = 'user'")
    op.execute("ALTER INDEX ix_user_message_user_id RENAME TO ix_investisseur_message_investisseur_id")
    op.alter_column(
        "user_message",
        "lu_par_user",
        new_column_name="lu_par_investisseur",
        existing_type=sa.Boolean(),
        existing_server_default=sa.false(),
    )
    op.alter_column(
        "user_message", "user_id", new_column_name="investisseur_id", existing_type=sa.UUID()
    )
    op.rename_table("user_message", "investisseur_message")
