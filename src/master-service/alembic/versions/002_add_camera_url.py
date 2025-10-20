"""add camera_url column

Revision ID: 002
Revises: 001
Create Date: 2025-10-20 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None

SCHEMA = 'master_service'


def upgrade() -> None:
    # Add camera_url column to camera_emails table
    op.add_column(
        'camera_emails',
        sa.Column('camera_url', sa.String(length=500), nullable=True),
        schema=SCHEMA
    )


def downgrade() -> None:
    # Remove camera_url column from camera_emails table
    op.drop_column('camera_emails', 'camera_url', schema=SCHEMA)

