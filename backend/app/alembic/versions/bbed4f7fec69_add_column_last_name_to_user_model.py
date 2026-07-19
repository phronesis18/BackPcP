"""Add column last_name to User model

Revision ID: bbed4f7fec69
Revises: d3e4f5a6b7c8
Create Date: 2026-07-17 19:35:33.250024

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'bbed4f7fec69'
down_revision = 'd3e4f5a6b7c8'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table('item')
    op.drop_index(op.f('ix_demande_owner_id'), table_name='demande')
    op.drop_index(op.f('ix_document_demande_id'), table_name='document')


def downgrade():
    op.create_index(op.f('ix_document_demande_id'), 'document', ['demande_id'], unique=False)
    op.create_index(op.f('ix_demande_owner_id'), 'demande', ['owner_id'], unique=False)
    op.create_table(
        'item',
        sa.Column('description', sa.VARCHAR(length=255), nullable=True),
        sa.Column('title', sa.VARCHAR(length=255), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('owner_id', sa.UUID(), nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['owner_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
