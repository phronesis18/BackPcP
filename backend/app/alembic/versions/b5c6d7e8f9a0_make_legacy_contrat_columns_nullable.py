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
    op.alter_column(
        "contrat", "plate", existing_type=sa.String(length=20), nullable=True
    )
    op.alter_column(
        "contrat", "gps_device_id", existing_type=sa.String(length=50), nullable=True
    )


def downgrade():
    op.alter_column(
        "contrat", "gps_device_id", existing_type=sa.String(length=50), nullable=False
    )
    op.alter_column(
        "contrat", "plate", existing_type=sa.String(length=20), nullable=False
    )
