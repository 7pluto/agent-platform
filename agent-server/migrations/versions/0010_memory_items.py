"""Add tenant/deployment/user scoped long-term memory.

Revision ID: 0010_memory_items
Revises: 0009_resource_registry
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0010_memory_items"
down_revision = "0009_resource_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_memory_item",
        sa.Column("memory_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("deployment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_run_id", postgresql.UUID(as_uuid=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_platform_memory_scope", "platform_memory_item", ["tenant_id", "deployment_id", "user_id"])
    op.execute(sa.text("ALTER TABLE platform_memory_item ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE platform_memory_item FORCE ROW LEVEL SECURITY"))
    op.execute(sa.text("CREATE POLICY platform_memory_item_tenant_isolation ON platform_memory_item USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"))


def downgrade() -> None:
    op.drop_table("platform_memory_item")
