"""Add external capability bindings and stable secret rotation state.

Revision ID: 0025_bindings_secret_rotation
Revises: 0024_resource_validation_runs
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0025_bindings_secret_rotation"
down_revision = "0024_resource_validation_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("platform_secret_vault", sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"))
    op.add_column("platform_secret_vault", sa.Column("last_used_at", sa.DateTime(timezone=True)))
    op.add_column("platform_secret_vault", sa.Column("rotated_at", sa.DateTime(timezone=True)))
    op.add_column("platform_secret_vault", sa.Column("disabled_at", sa.DateTime(timezone=True)))
    op.create_table(
        "platform_resource_external_binding",
        sa.Column("binding_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("connection_resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_type", sa.String(32), nullable=False),
        sa.Column("external_id", sa.String(256), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="MANAGED"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["connection_resource_id"], ["platform_resource_definition.resource_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resource_id"], ["platform_resource_definition.resource_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "provider", "connection_resource_id", "external_type", "external_id", name="uq_platform_resource_external_binding"),
    )
    op.create_index("ix_platform_resource_external_binding_tenant_connection", "platform_resource_external_binding", ["tenant_id", "connection_resource_id"])
    op.execute(sa.text("ALTER TABLE platform_resource_external_binding ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE platform_resource_external_binding FORCE ROW LEVEL SECURITY"))
    op.execute(sa.text("CREATE POLICY platform_resource_external_binding_tenant_isolation ON platform_resource_external_binding USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"))


def downgrade() -> None:
    op.drop_table("platform_resource_external_binding")
    for name in ("disabled_at", "rotated_at", "last_used_at", "status"):
        op.drop_column("platform_secret_vault", name)
