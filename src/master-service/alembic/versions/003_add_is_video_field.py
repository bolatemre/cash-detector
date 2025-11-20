"""add is_video field to camera table

Revision ID: 003
Revises: 002
Create Date: 2025-01-20 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None

SCHEMA = 'master_service'


def upgrade() -> None:
    # Add is_video column to camera table
    op.add_column('camera', sa.Column('is_video', sa.Boolean(), nullable=False, server_default='false'), schema=SCHEMA)
    
    # Update existing records: set is_video=True for cameras with camera_id starting with 'VID'
    op.execute(f"UPDATE {SCHEMA}.camera SET is_video = true WHERE camera_id LIKE 'VID%'")


def downgrade() -> None:
    # Remove is_video column
    op.drop_column('camera', 'is_video', schema=SCHEMA)

