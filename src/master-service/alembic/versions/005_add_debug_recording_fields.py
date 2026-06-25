"""add debug recording fields to camera table

Revision ID: 005
Revises: 004
Create Date: 2026-06-25 15:45:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None

SCHEMA = 'master_service'


def upgrade() -> None:
    # Add per-camera debug recording settings
    op.add_column(
        'camera',
        sa.Column('debug_enabled', sa.Boolean(), nullable=False, server_default='false'),
        schema=SCHEMA,
    )
    op.add_column(
        'camera',
        sa.Column('debug_segment_duration', sa.Integer(), nullable=True, server_default='3600'),
        schema=SCHEMA,
    )
    op.add_column(
        'camera',
        sa.Column('debug_minio_folder', sa.String(length=100), nullable=True, server_default='debug'),
        schema=SCHEMA,
    )

    # Backfill existing rows
    op.execute(f"UPDATE {SCHEMA}.camera SET debug_enabled = false WHERE debug_enabled IS NULL")
    op.execute(f"UPDATE {SCHEMA}.camera SET debug_segment_duration = 3600 WHERE debug_segment_duration IS NULL")
    op.execute(f"UPDATE {SCHEMA}.camera SET debug_minio_folder = 'debug' WHERE debug_minio_folder IS NULL")


def downgrade() -> None:
    # Remove per-camera debug recording settings
    op.drop_column('camera', 'debug_minio_folder', schema=SCHEMA)
    op.drop_column('camera', 'debug_segment_duration', schema=SCHEMA)
    op.drop_column('camera', 'debug_enabled', schema=SCHEMA)
