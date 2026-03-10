"""add email_notifications to users

Revision ID: 010
Revises: 009
Create Date: 2026-03-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_notifications", sa.Boolean(), server_default="true", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "email_notifications")
