"""Add product semantics to resource descriptors.

Revision ID: 0020_resource_semantics
Revises: 0019_resource_descriptors
"""
from alembic import op
import sqlalchemy as sa


revision = "0020_resource_semantics"
down_revision = "0019_resource_descriptors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("platform_resource_descriptor", sa.Column("one_line_summary", sa.String(256)))
    op.add_column("platform_resource_descriptor", sa.Column("when_to_use", sa.Text()))
    op.add_column("platform_resource_descriptor", sa.Column("when_not_to_use", sa.Text()))
    op.add_column("platform_resource_descriptor", sa.Column("input_summary", sa.Text()))
    op.add_column("platform_resource_descriptor", sa.Column("output_summary", sa.Text()))
    op.add_column("platform_resource_descriptor", sa.Column("risk_level", sa.String(16), nullable=False, server_default="LOW"))
    op.add_column("platform_resource_descriptor", sa.Column("read_only", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.execute("UPDATE platform_resource_descriptor SET one_line_summary = usage_guidance WHERE usage_guidance IS NOT NULL")


def downgrade() -> None:
    for name in ("read_only", "risk_level", "output_summary", "input_summary", "when_not_to_use", "when_to_use", "one_line_summary"):
        op.drop_column("platform_resource_descriptor", name)
