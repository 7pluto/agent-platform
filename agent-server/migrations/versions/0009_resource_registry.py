"""Add unified AI resource registry.

Revision ID: 0009_resource_registry
Revises: 0008_model_availability
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009_resource_registry"
down_revision = "0008_model_availability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    payload = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")
    op.create_table(
        "platform_resource_definition",
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("resource_type", sa.String(32), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("draft_config", payload, nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "resource_type", "slug", name="uq_platform_resource_definition_slug"),
    )
    op.create_index("ix_platform_resource_definition_tenant_type", "platform_resource_definition", ["tenant_id", "resource_type"])
    op.create_table(
        "platform_resource_version",
        sa.Column("resource_version_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("platform_resource_definition.resource_id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("resource_type", sa.String(32), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("config", payload, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("tenant_id", "resource_id", "version_number", name="uq_platform_resource_version_number"),
    )
    op.create_index("ix_platform_resource_version_tenant_resource", "platform_resource_version", ["tenant_id", "resource_id"])
    for table in ("platform_resource_definition", "platform_resource_version"):
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"CREATE POLICY {table}_tenant_isolation ON {table} USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"))


def downgrade() -> None:
    op.drop_index("ix_platform_resource_version_tenant_resource", table_name="platform_resource_version")
    op.drop_table("platform_resource_version")
    op.drop_index("ix_platform_resource_definition_tenant_type", table_name="platform_resource_definition")
    op.drop_table("platform_resource_definition")
