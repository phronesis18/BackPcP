"""Create grilletauxduree table and drop the flat teg/apport from parametresfinanciers

Revision ID: a2b3c4d5e6f7
Revises: c6d7e8f9a0b1
Create Date: 2026-09-14 09:00:00.000000

"""
import uuid

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a2b3c4d5e6f7"
down_revision = "c6d7e8f9a0b1"
branch_labels = None
depends_on = None

# Grille validée par le Comité de Crédit : le TEG et l'apport minimum requis
# dépendent désormais de la durée choisie, au lieu d'un taux unique appliqué
# à toutes les durées.
GRILLE_TAUX_DEFAUT = [
    {"duree_mois": 24, "taux_teg_annuel": 20.0, "taux_apport_min": 0.20},
    {"duree_mois": 36, "taux_teg_annuel": 21.0, "taux_apport_min": 0.22},
    {"duree_mois": 48, "taux_teg_annuel": 22.0, "taux_apport_min": 0.25},
    {"duree_mois": 60, "taux_teg_annuel": 22.0, "taux_apport_min": 0.27},
    {"duree_mois": 72, "taux_teg_annuel": 22.0, "taux_apport_min": 0.30},
    {"duree_mois": 84, "taux_teg_annuel": 22.0, "taux_apport_min": 0.40},
    {"duree_mois": 96, "taux_teg_annuel": 22.0, "taux_apport_min": 0.50},
]

grille_table = sa.table(
    "grilletauxduree",
    sa.column("id", sa.UUID()),
    sa.column("duree_mois", sa.Integer()),
    sa.column("taux_teg_annuel", sa.Float()),
    sa.column("taux_apport_min", sa.Float()),
)


def upgrade():
    op.create_table(
        "grilletauxduree",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("duree_mois", sa.Integer(), nullable=False),
        sa.Column("taux_teg_annuel", sa.Float(), nullable=False),
        sa.Column("taux_apport_min", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("duree_mois", name="uq_grilletauxduree_duree_mois"),
    )
    op.create_index(
        op.f("ix_grilletauxduree_duree_mois"), "grilletauxduree", ["duree_mois"]
    )

    op.bulk_insert(
        grille_table,
        [{"id": uuid.uuid4(), **row} for row in GRILLE_TAUX_DEFAUT],
    )

    op.drop_column("parametresfinanciers", "taux_teg_annuel")
    op.drop_column("parametresfinanciers", "taux_apport")


def downgrade():
    op.add_column(
        "parametresfinanciers",
        sa.Column(
            "taux_teg_annuel", sa.Float(), nullable=False, server_default="22.0"
        ),
    )
    op.add_column(
        "parametresfinanciers",
        sa.Column("taux_apport", sa.Float(), nullable=False, server_default="0.25"),
    )

    op.drop_index(op.f("ix_grilletauxduree_duree_mois"), table_name="grilletauxduree")
    op.drop_table("grilletauxduree")
