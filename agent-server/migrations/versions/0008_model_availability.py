"""Add model connection availability state.

Revision ID: 0008_model_availability
Revises: 0007_model_resources
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_model_availability"
down_revision = "0007_model_resources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("platform_model_version", sa.Column("availability", sa.String(32), nullable=False, server_default="UNKNOWN"))
    op.add_column("platform_model_version", sa.Column("last_tested_at", sa.DateTime(timezone=True)))
    op.add_column("platform_model_version", sa.Column("last_test_error", sa.Text()))


def downgrade() -> None:
    op.drop_column("platform_model_version", "last_test_error")
    op.drop_column("platform_model_version", "last_tested_at")
    op.drop_column("platform_model_version", "availability")