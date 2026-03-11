"""add status and owner_id to favorites

Revision ID: 011
Revises: 010
Create Date: 2026-03-11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

favorite_status = sa.Enum("to_contact", "visit_planned", "offer_made", name="favoritestatus")


def upgrade() -> None:
    favorite_status.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "favorites",
        sa.Column("status", favorite_status, nullable=False, server_default="to_contact"),
    )
    op.add_column(
        "favorites",
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("ix_favorites_status", "favorites", ["status"])
    op.create_index("ix_favorites_owner_id", "favorites", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_favorites_owner_id", table_name="favorites")
    op.drop_index("ix_favorites_status", table_name="favorites")
    op.drop_column("favorites", "owner_id")
    op.drop_column("favorites", "status")
    favorite_status.drop(op.get_bind(), checkfirst=True)
