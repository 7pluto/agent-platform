"""Persist the RuoYi audience selected when publishing an Agent deployment.

Revision ID: 0023_deployment_pub_profile
Revises: 0022_resource_pub_profile
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0023_deployment_pub_profile"
down_revision = "0022_resource_pub_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_deployment_publication_profile",
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("deployment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("publication_scope", sa.String(32), nullable=False, server_default="PERSONAL"),
        sa.Column("subject_bindings", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("generated_grant_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("updated_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["deployment_id"], ["platform_deployment.deployment_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "deployment_id", name="uq_platform_deployment_publication_profile"),
    )
    op.create_index("ix_platform_deployment_publication_profile_tenant", "platform_deployment_publication_profile", ["tenant_id"])
    op.execute(sa.text("ALTER TABLE platform_deployment_publication_profile ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE platform_deployment_publication_profile FORCE ROW LEVEL SECURITY"))
    op.execute(sa.text("CREATE POLICY platform_deployment_publication_profile_tenant_isolation ON platform_deployment_publication_profile USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"))


def downgrade() -> None:
    op.drop_table("platform_deployment_publication_profile")
