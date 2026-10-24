"""Add saved offer and renovation budgets to household favorites.

Revision ID: 020
Revises: 019
"""

import sqlalchemy as sa
from alembic import op

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "favorites", sa.Column("offer_price", sa.Numeric(12, 2), nullable=True)
    )
    op.add_column(
        "favorites", sa.Column("renovation_budget", sa.Numeric(12, 2), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("favorites", "renovation_budget")
    op.drop_column("favorites", "offer_price")
