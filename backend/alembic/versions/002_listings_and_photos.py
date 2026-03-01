"""listings, photos, price_history

Revision ID: 002
Revises: 001
Create Date: 2026-02-28
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "listings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("household_id", sa.Integer(), sa.ForeignKey("households.id"), nullable=False, index=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("source_id", sa.String(255)),
        sa.Column("external_url", sa.String(1024)),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("price", sa.Float()),
        sa.Column("sqm", sa.Float()),
        sa.Column("price_per_sqm", sa.Float()),
        sa.Column("bedrooms", sa.Integer()),
        sa.Column("city", sa.String(255)),
        sa.Column("district", sa.String(255)),
        sa.Column("location_detail", sa.String(512)),
        sa.Column("fingerprint", sa.String(64), index=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "listing_photos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("listing_id", sa.Integer(), sa.ForeignKey("listings.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("s3_key", sa.String(512), nullable=False),
        sa.Column("original_url", sa.String(1024)),
        sa.Column("phash", sa.String(64)),
        sa.Column("position", sa.Integer(), server_default="0"),
    )

    op.create_table(
        "price_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("listing_id", sa.Integer(), sa.ForeignKey("listings.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("price_history")
    op.drop_table("listing_photos")
    op.drop_table("listings")
