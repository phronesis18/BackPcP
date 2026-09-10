"""Change seuil_scoring_auto semantics from a /850 score to a 0-100 percentage

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-09-10 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e6f7a8b9c0d1"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None

parametres_table = sa.table(
    "parametresfinanciers",
    sa.column("seuil_scoring_auto", sa.Integer()),
)


def upgrade():
    op.alter_column(
        "parametresfinanciers", "seuil_scoring_auto", server_default="75"
    )
    # Any value already saved under the old /850 scale is necessarily > 100
    # (real-world thresholds sit in the 50-80% range, i.e. 425-680 on the old
    # scale) — convert those in place so admins don't have to re-enter it.
    connection = op.get_bind()
    connection.execute(
        parametres_table.update()
        .where(parametres_table.c.seuil_scoring_auto > 100)
        .values(
            seuil_scoring_auto=sa.func.round(
                parametres_table.c.seuil_scoring_auto * 100.0 / 850
            )
        )
    )


def downgrade():
    op.alter_column(
        "parametresfinanciers", "seuil_scoring_auto", server_default="650"
    )
    connection = op.get_bind()
    connection.execute(
        parametres_table.update().values(
            seuil_scoring_auto=sa.func.round(
                parametres_table.c.seuil_scoring_auto * 850.0 / 100
            )
        )
    )
