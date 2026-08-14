"""Add shared business publication profile to resource descriptors.

Revision ID: 0022_resource_pub_profile
Revises: 0021_resource_semantics_backfill
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0022_resource_pub_profile"
down_revision = "0021_resource_semantics_backfill"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("platform_resource_descriptor", sa.Column("business_line", sa.String(128)))
    op.add_column("platform_resource_descriptor", sa.Column("data_involved", sa.Text()))
    op.add_column("platform_resource_descriptor", sa.Column("audience", sa.Text()))
    op.add_column("platform_resource_descriptor", sa.Column("usage_scenarios", sa.Text()))
    op.add_column("platform_resource_descriptor", sa.Column("developer_user_ids", postgresql.JSONB(), nullable=False, server_default="[]"))
    op.add_column("platform_resource_descriptor", sa.Column("publication_scope", sa.String(32), nullable=False, server_default="PERSONAL"))


def downgrade() -> None:
    for name in ("publication_scope", "developer_user_ids", "usage_scenarios", "audience", "data_involved", "business_line"):
        op.drop_column("platform_resource_descriptor", name)
