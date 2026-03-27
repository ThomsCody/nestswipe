"""add contact fields to listings

Revision ID: 014
Revises: 013
Create Date: 2026-03-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("contact_phone", sa.String(50), nullable=True))
    op.add_column("listings", sa.Column("agency_name", sa.String(255), nullable=True))
    op.add_column("listings", sa.Column("agent_name", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("listings", "agent_name")
    op.drop_column("listings", "agency_name")
    op.drop_column("listings", "contact_phone")
