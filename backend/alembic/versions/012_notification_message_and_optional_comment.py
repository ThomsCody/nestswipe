"""make notification comment_id optional, add message column

Revision ID: 012
Revises: 011
Create Date: 2026-03-11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("notifications", "comment_id", existing_type=sa.Integer(), nullable=True)
    op.add_column("notifications", sa.Column("message", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("notifications", "message")
    op.alter_column("notifications", "comment_id", existing_type=sa.Integer(), nullable=False)
