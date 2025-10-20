"""initial schema

Revision ID: 001
Revises: 
Create Date: 2025-10-20 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None

SCHEMA = 'master_service'


def upgrade() -> None:
    # Create schema
    op.execute(f'CREATE SCHEMA IF NOT EXISTS {SCHEMA}')
    
    # Create camera_emails table
    op.create_table(
        'camera_emails',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('camera_id', sa.String(length=100), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        schema=SCHEMA
    )
    
    # Create indexes
    op.create_index('ix_camera_emails_id', 'camera_emails', ['id'], unique=False, schema=SCHEMA)
    op.create_index('ix_camera_emails_camera_id', 'camera_emails', ['camera_id'], unique=True, schema=SCHEMA)


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_camera_emails_camera_id', table_name='camera_emails', schema=SCHEMA)
    op.drop_index('ix_camera_emails_id', table_name='camera_emails', schema=SCHEMA)
    
    # Drop table
    op.drop_table('camera_emails', schema=SCHEMA)
    
    # Drop schema
    op.execute(f'DROP SCHEMA IF EXISTS {SCHEMA}')

