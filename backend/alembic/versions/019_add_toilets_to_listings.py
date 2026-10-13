"""Add the number of WC to listings.

Revision ID: 019
Revises: 018
"""

import sqlalchemy as sa
from alembic import op

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("toilets", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("listings", "toilets")
