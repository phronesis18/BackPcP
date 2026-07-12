"""Add phone to User

Revision ID: a3b7c1d2e4f5
Revises: fe56fa70289e
Create Date: 2026-07-09 23:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = "a3b7c1d2e4f5"
down_revision = "fe56fa70289e"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "user",
        sa.Column("phone", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=True),
    )
    op.create_index(op.f("ix_user_phone"), "user", ["phone"], unique=True)


def downgrade():
    op.drop_index(op.f("ix_user_phone"), table_name="user")
    op.drop_column("user", "phone")
