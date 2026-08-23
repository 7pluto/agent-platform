"""Add immutable provider discovery snapshots.

Revision ID: 0026_discovery_snapshots
Revises: 0025_bindings_secret_rotation
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0026_discovery_snapshots"
down_revision = "0025_bindings_secret_rotation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_resource_discovery_snapshot",
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("resource_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("external_type", sa.String(32), nullable=False),
        sa.Column("external_id", sa.String(256), nullable=False),
        sa.Column("schema_hash", sa.String(64), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["resource_version_id"], ["platform_resource_version.resource_version_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "resource_version_id", name="uq_platform_resource_discovery_snapshot"),
    )
    op.create_index(
        "ix_platform_resource_discovery_snapshot_tenant_version",
        "platform_resource_discovery_snapshot",
        ["tenant_id", "resource_version_id"],
    )
    op.execute(sa.text("ALTER TABLE platform_resource_discovery_snapshot ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE platform_resource_discovery_snapshot FORCE ROW LEVEL SECURITY"))
    op.execute(sa.text(
        "CREATE POLICY platform_resource_discovery_snapshot_tenant_isolation "
        "ON platform_resource_discovery_snapshot "
        "USING (tenant_id = current_setting('app.tenant_id', true)) "
        "WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"
    ))


def downgrade() -> None:
    op.drop_table("platform_resource_discovery_snapshot")
