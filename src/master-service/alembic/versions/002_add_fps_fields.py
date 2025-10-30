"""add fps fields to camera table

Revision ID: 002
Revises: 001
Create Date: 2025-10-28 12:00:00.000000

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
    # Add FPS columns to camera table
    op.add_column('camera', sa.Column('expected_fps', sa.Integer(), nullable=True, default=25), schema=SCHEMA)
    op.add_column('camera', sa.Column('record_fps', sa.Integer(), nullable=True, default=20), schema=SCHEMA)
    
    # Update existing records with default values
    op.execute(f"UPDATE {SCHEMA}.camera SET expected_fps = 25 WHERE expected_fps IS NULL")
    op.execute(f"UPDATE {SCHEMA}.camera SET record_fps = 20 WHERE record_fps IS NULL")


def downgrade() -> None:
    # Remove FPS columns
    op.drop_column('camera', 'record_fps', schema=SCHEMA)
    op.drop_column('camera', 'expected_fps', schema=SCHEMA)
