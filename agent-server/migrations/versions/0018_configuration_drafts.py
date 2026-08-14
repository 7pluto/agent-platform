"""Add deployment configuration drafts for the Agent workbench.

Revision ID: 0018_configuration_drafts
Revises: 0017_conversation_workbench
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0018_configuration_drafts"
down_revision = "0017_conversation_workbench"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_deployment_configuration_draft",
        sa.Column("draft_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("deployment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("base_revision_id", postgresql.UUID(as_uuid=True)),
        sa.Column("specification", postgresql.JSONB(), nullable=False),
        sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "deployment_id", name="uq_platform_deployment_configuration_draft"),
    )
    op.create_index("ix_platform_deployment_configuration_draft_tenant_id", "platform_deployment_configuration_draft", ["tenant_id"])
    op.execute(sa.text("ALTER TABLE platform_deployment_configuration_draft ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE platform_deployment_configuration_draft FORCE ROW LEVEL SECURITY"))
    op.execute(sa.text("CREATE POLICY platform_deployment_configuration_draft_tenant_isolation ON platform_deployment_configuration_draft USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"))


def downgrade() -> None:
    op.drop_table("platform_deployment_configuration_draft")
