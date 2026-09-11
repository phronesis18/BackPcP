"""Create vehiculeflotte table (fleet monitor module)

Revision ID: a1b2c3d4e5f6
Revises: f7a8b9c0d1e2
Create Date: 2026-09-11 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "vehiculeflotte",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("demande_id", sa.UUID(), nullable=False),
        sa.Column("plaque", sa.String(length=20), nullable=True),
        sa.Column("position_label", sa.String(length=120), nullable=True),
        sa.Column("position_maj_le", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["demande_id"], ["demande.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("demande_id"),
    )


def downgrade():
    op.drop_table("vehiculeflotte")
