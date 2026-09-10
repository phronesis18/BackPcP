"""Add plate, gps_device_id and cutoff_active to Contrat (Fleet Monitor)

Revision ID: d4e5f6a7b8c9
Revises: c4d5e6f7a8b9
Create Date: 2026-09-10 09:00:00.000000

"""
import uuid

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d4e5f6a7b8c9"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


_PLATE_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"


def _generate_plate(contrat_id: uuid.UUID) -> str:
    h = contrat_id.int
    n = len(_PLATE_LETTERS)
    l1 = _PLATE_LETTERS[h % n]
    l2 = _PLATE_LETTERS[(h // n) % n]
    num = (h // (n * n)) % 10000
    l3 = _PLATE_LETTERS[(h // (n * n * 10000)) % n]
    l4 = _PLATE_LETTERS[(h // (n * n * 10000 * n)) % n]
    return f"{l1}{l2} {num:04d} {l3}{l4}"


def _generate_gps_device_id(contrat_id: uuid.UUID) -> str:
    return str(contrat_id.int % 10**15).rjust(15, "3")


def upgrade():
    op.add_column("contrat", sa.Column("plate", sa.String(length=20), nullable=True))
    op.add_column("contrat", sa.Column("gps_device_id", sa.String(length=50), nullable=True))
    op.add_column(
        "contrat",
        sa.Column("cutoff_active", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id FROM contrat")).fetchall()
    for (raw_id,) in rows:
        contrat_id = raw_id if isinstance(raw_id, uuid.UUID) else uuid.UUID(str(raw_id))
        connection.execute(
            sa.text("UPDATE contrat SET plate = :plate, gps_device_id = :gps WHERE id = :id"),
            {
                "plate": _generate_plate(contrat_id),
                "gps": _generate_gps_device_id(contrat_id),
                "id": contrat_id,
            },
        )

    op.alter_column("contrat", "plate", nullable=False)
    op.alter_column("contrat", "gps_device_id", nullable=False)
    op.create_unique_constraint("uq_contrat_plate", "contrat", ["plate"])
    op.create_unique_constraint("uq_contrat_gps_device_id", "contrat", ["gps_device_id"])


def downgrade():
    op.drop_constraint("uq_contrat_gps_device_id", "contrat", type_="unique")
    op.drop_constraint("uq_contrat_plate", "contrat", type_="unique")
    op.drop_column("contrat", "cutoff_active")
    op.drop_column("contrat", "gps_device_id")
    op.drop_column("contrat", "plate")
