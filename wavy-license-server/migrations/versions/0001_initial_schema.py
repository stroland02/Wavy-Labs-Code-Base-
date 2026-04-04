"""initial schema — customers and licenses tables

Revision ID: 0001
Revises:
Create Date: 2026-03-03
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("id",              sa.String(36),  primary_key=True),
        sa.Column("email",           sa.String(255), nullable=False, unique=True),
        sa.Column("stripe_customer", sa.String(64),  nullable=True,  unique=True),
        sa.Column("created_at",      sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_customers_email", "customers", ["email"])

    op.create_table(
        "licenses",
        sa.Column("id",             sa.String(36),  primary_key=True),
        sa.Column("customer_id",    sa.String(36),
                  sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("key",            sa.String(64),  nullable=False, unique=True),
        sa.Column("tier",           sa.Enum("free", "pro", "studio", name="tierenum"),
                  nullable=False, server_default="free"),
        sa.Column("stripe_sub_id",  sa.String(64),  nullable=True),
        sa.Column("active",         sa.Boolean(),   nullable=False, server_default="1"),
        sa.Column("created_at",     sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at",     sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_validated", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activations",    sa.Integer(),   nullable=False, server_default="0"),
        sa.Column("notes",          sa.Text(),      nullable=True),
    )
    op.create_index("ix_licenses_key",         "licenses", ["key"])
    op.create_index("ix_licenses_customer_id", "licenses", ["customer_id"])


def downgrade() -> None:
    op.drop_table("licenses")
    op.drop_table("customers")
    op.execute("DROP TYPE IF EXISTS tierenum")
