"""initial schema

Revision ID: 001
Revises: 
Create Date: 2025-10-16 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create events table
    op.create_table(
        'events',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('camera_id', sa.String(length=100), nullable=False),
        sa.Column('detected_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('video_url', sa.Text(), nullable=True),
        sa.Column('video_filename', sa.String(length=255), nullable=True),
        sa.Column('notification_sent', sa.Boolean(), nullable=True, server_default=sa.text('false')),
        sa.Column('notification_sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index('ix_events_camera_id', 'events', ['camera_id'], unique=False)
    op.create_index('ix_events_detected_at', 'events', ['detected_at'], unique=False)
    op.create_index('ix_events_event_type', 'events', ['event_type'], unique=False)


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_events_event_type', table_name='events')
    op.drop_index('ix_events_detected_at', table_name='events')
    op.drop_index('ix_events_camera_id', table_name='events')
    
    # Drop table
    op.drop_table('events')
