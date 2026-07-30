"""set camera buffersize default to zero

Revision ID: 006
Revises: 005
Create Date: 2026-06-25 15:47:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None

SCHEMA = 'master_service'


def upgrade() -> None:
    # Change default to 0 for new rows and backfill NULL values
    op.execute(
        f"ALTER TABLE {SCHEMA}.camera ALTER COLUMN buffersize SET DEFAULT 0"
    )
    op.execute(
        f"UPDATE {SCHEMA}.camera SET buffersize = 0 WHERE buffersize IS NULL"
    )


def downgrade() -> None:
    # Restore previous default value
    op.execute(
        f"ALTER TABLE {SCHEMA}.camera ALTER COLUMN buffersize SET DEFAULT 1"
    )
