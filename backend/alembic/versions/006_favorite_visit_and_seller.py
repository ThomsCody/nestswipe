"""favorite visit and seller

Revision ID: 006
Revises: 005
Create Date: 2026-03-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("favorites", sa.Column("visit_date", sa.DateTime(timezone=True), nullable=True))
    op.add_column("favorites", sa.Column("location", sa.String(500), nullable=True))
    op.add_column("favorites", sa.Column("seller_name", sa.String(255), nullable=True))
    op.add_column("favorites", sa.Column("seller_phone", sa.String(50), nullable=True))
    op.add_column("favorites", sa.Column("seller_is_agency", sa.Boolean(), server_default="false", nullable=True))


def downgrade() -> None:
    op.drop_column("favorites", "seller_is_agency")
    op.drop_column("favorites", "seller_phone")
    op.drop_column("favorites", "seller_name")
    op.drop_column("favorites", "location")
    op.drop_column("favorites", "visit_date")
