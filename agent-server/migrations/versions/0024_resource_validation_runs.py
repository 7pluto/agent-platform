"""Persist external resource validation outcomes.

Revision ID: 0024_resource_validation_runs
Revises: 0023_deployment_pub_profile
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0024_resource_validation_runs"
down_revision = "0023_deployment_pub_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_resource_validation_run",
        sa.Column("validation_run_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("resource_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("validation_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["resource_version_id"], ["platform_resource_version.resource_version_id"], ondelete="CASCADE"),
    )
    op.create_index("ix_platform_resource_validation_run_tenant_version", "platform_resource_validation_run", ["tenant_id", "resource_version_id", "created_at"])
    op.execute(sa.text("ALTER TABLE platform_resource_validation_run ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE platform_resource_validation_run FORCE ROW LEVEL SECURITY"))
    op.execute(sa.text("CREATE POLICY platform_resource_validation_run_tenant_isolation ON platform_resource_validation_run USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"))


def downgrade() -> None:
    op.drop_table("platform_resource_validation_run")
