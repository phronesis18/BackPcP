"""Make legacy contrat.plate/gps_device_id nullable

These two columns exist in the database as NOT NULL/UNIQUE but are not part
of the current Contrat model (app/models.py) — no route or crud function
populates them. That schema drift (likely from an earlier, now-abandoned
implementation of the fleet/recouvrement domain) silently broke contract
signing: every INSERT into `contrat` failed with a NotNullViolation. Making
them nullable unblocks signing without touching the two existing rows that
already have values.

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-09-11 22:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b5c6d7e8f9a0"
down_revision = "a4b5c6d7e8f9"
branch_labels = None
depends_on = None


def upgrade():
    # Fresh databases built purely from this migration history never had
    # these columns in the first place (only environments with the manual
    # schema drift described above do) — skip instead of failing on them.
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("contrat")}
    if "plate" in columns:
        op.alter_column(
            "contrat", "plate", existing_type=sa.String(length=20), nullable=True
        )
    if "gps_device_id" in columns:
        op.alter_column(
            "contrat", "gps_device_id", existing_type=sa.String(length=50), nullable=True
        )


def downgrade():
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("contrat")}
    if "gps_device_id" in columns:
        op.alter_column(
            "contrat", "gps_device_id", existing_type=sa.String(length=50), nullable=False
        )
    if "plate" in columns:
        op.alter_column(
            "contrat", "plate", existing_type=sa.String(length=20), nullable=False
        )
