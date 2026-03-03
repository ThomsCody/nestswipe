"""add user_id to listings

Revision ID: 008
Revises: 007
Create Date: 2026-03-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add user_id column as nullable first
    op.add_column("listings", sa.Column("user_id", sa.Integer(), nullable=True))

    # Backfill: set user_id to any member of the listing's household
    op.execute(
        """
        UPDATE listings
        SET user_id = (
            SELECT u.id FROM users u
            WHERE u.household_id = listings.household_id
            ORDER BY u.id
            LIMIT 1
        )
        """
    )

    # Make NOT NULL and add FK + index
    op.alter_column("listings", "user_id", nullable=False)
    op.create_foreign_key("fk_listings_user_id", "listings", "users", ["user_id"], ["id"])
    op.create_index("ix_listings_user_id", "listings", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_listings_user_id", table_name="listings")
    op.drop_constraint("fk_listings_user_id", "listings", type_="foreignkey")
    op.drop_column("listings", "user_id")
