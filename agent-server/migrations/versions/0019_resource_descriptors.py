"""Add product metadata for resources without rewriting legacy models.

Revision ID: 0019_resource_descriptors
Revises: 0018_configuration_drafts
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0019_resource_descriptors"
down_revision = "0018_configuration_drafts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.create_table(
        "platform_resource_descriptor",
        sa.Column("descriptor_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("resource_type", sa.String(32), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", sa.String(128), nullable=False),
        sa.Column("owner_dept_id", sa.String(128)),
        sa.Column("source_type", sa.String(32), nullable=False, server_default="PLATFORM_NATIVE"),
        sa.Column("source_ref", sa.String(256)),
        sa.Column("usage_guidance", sa.Text()),
        sa.Column("tags", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("lifecycle_status", sa.String(32), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "resource_type", "resource_id", name="uq_platform_resource_descriptor_target"),
    )
    op.create_index("ix_platform_resource_descriptor_tenant_type", "platform_resource_descriptor", ["tenant_id", "resource_type"])
    # Registry definitions have a trustworthy creator. Legacy Models are marked
    # as historical imports until an administrator explicitly transfers them.
    op.execute(sa.text("""
        INSERT INTO platform_resource_descriptor
          (descriptor_id, tenant_id, resource_type, resource_id, owner_user_id, source_type)
        SELECT gen_random_uuid(), tenant_id, resource_type, resource_id, created_by,
               CASE WHEN draft_config->>'kind' = 'DIFY_FLOW' THEN 'DIFY'
                    WHEN draft_config->>'kind' = 'MCP' THEN 'MCP'
                    WHEN draft_config->>'kind' = 'NATIVE' THEN 'PLATFORM_NATIVE'
                    ELSE 'PLATFORM_NATIVE' END
        FROM platform_resource_definition
    """))
    op.execute(sa.text("""
        INSERT INTO platform_resource_descriptor
          (descriptor_id, tenant_id, resource_type, resource_id, owner_user_id, source_type, lifecycle_status)
        SELECT gen_random_uuid(), tenant_id, 'MODEL', model_id, 'legacy-import', 'OPENAI_COMPATIBLE', 'ACTIVE'
        FROM platform_model_definition
    """))
    op.execute(sa.text("ALTER TABLE platform_resource_descriptor ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE platform_resource_descriptor FORCE ROW LEVEL SECURITY"))
    op.execute(sa.text("CREATE POLICY platform_resource_descriptor_tenant_isolation ON platform_resource_descriptor USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"))


def downgrade() -> None:
    op.drop_table("platform_resource_descriptor")
