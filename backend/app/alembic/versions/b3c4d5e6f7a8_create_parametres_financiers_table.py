"""Create parametresfinanciers table

Revision ID: b3c4d5e6f7a8
Revises: a7b8c9d0e1f2
Create Date: 2026-09-06 09:00:00.000000

"""
import uuid

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b3c4d5e6f7a8"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "parametresfinanciers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("taux_teg_annuel", sa.Float(), nullable=False, server_default="22.0"),
        sa.Column("taux_apport", sa.Float(), nullable=False, server_default="0.25"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    parametres_table = sa.table(
        "parametresfinanciers",
        sa.column("id", sa.UUID()),
        sa.column("taux_teg_annuel", sa.Float()),
        sa.column("taux_apport", sa.Float()),
    )
    op.bulk_insert(
        parametres_table,
        [{"id": uuid.uuid4(), "taux_teg_annuel": 22.0, "taux_apport": 0.25}],
    )


def downgrade():
    op.drop_table("parametresfinanciers")
