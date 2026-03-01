"""add floor and rooms to listings

Revision ID: 007
Revises: 006
Create Date: 2026-03-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("rooms", sa.Integer(), nullable=True))
    op.add_column("listings", sa.Column("floor", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("listings", "floor")
    op.drop_column("listings", "rooms")
