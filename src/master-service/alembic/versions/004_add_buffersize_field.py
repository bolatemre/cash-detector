"""add buffersize field to camera table

Revision ID: 004
Revises: 003
Create Date: 2025-01-20 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None

SCHEMA = 'master_service'


def upgrade() -> None:
    # Add buffersize column to camera table
    op.add_column('camera', sa.Column('buffersize', sa.Integer(), nullable=True, server_default='1'), schema=SCHEMA)
    
    # Update existing records with default value
    op.execute(f"UPDATE {SCHEMA}.camera SET buffersize = 1 WHERE buffersize IS NULL")


def downgrade() -> None:
    # Remove buffersize column
    op.drop_column('camera', 'buffersize', schema=SCHEMA)

