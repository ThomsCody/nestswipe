"""add nogo value to favoritestatus enum

Revision ID: 013
Revises: 012
Create Date: 2026-03-16
"""

from typing import Sequence, Union

from alembic import op

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ALTER TYPE ADD VALUE cannot run inside a transaction in PostgreSQL.
    # Commit the current transaction first, then run outside it.
    op.execute("COMMIT")
    op.execute("ALTER TYPE favoritestatus ADD VALUE IF NOT EXISTS 'nogo' AFTER 'offer_made'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values; a full enum rebuild
    # would be needed. Leaving as-is since the extra value is harmless.
    pass
