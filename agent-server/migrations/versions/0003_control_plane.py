"""Create tenant-scoped Agent control-plane tables.

Revision ID: 0003_control_plane
Revises: 0002_run_event_thread
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003_control_plane"
down_revision: Union[str, None] = "0002_run_event_thread"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TENANT_TABLES = (
    "platform_agent_definition",
    "platform_agent_version",
    "platform_deployment",
    "platform_deployment_revision",
)


def upgrade() -> None:
    op.create_table(
        "platform_agent_definition",
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("draft_spec", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_platform_agent_definition_slug"),
    )
    op.create_index("ix_platform_agent_definition_tenant_id", "platform_agent_definition", ["tenant_id"])

    op.create_table(
        "platform_agent_version",
        sa.Column("agent_version_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_agent_definition.agent_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("specification", postgresql.JSONB(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("tenant_id", "agent_id", "version_number", name="uq_platform_agent_version_number"),
    )
    op.create_index("ix_platform_agent_version_tenant_id", "platform_agent_version", ["tenant_id"])
    op.create_index("ix_platform_agent_version_tenant_agent", "platform_agent_version", ["tenant_id", "agent_id"])

    op.create_table(
        "platform_deployment",
        sa.Column("deployment_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_agent_definition.agent_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("active_revision_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "name", name="uq_platform_deployment_name"),
    )
    op.create_index("ix_platform_deployment_tenant_id", "platform_deployment", ["tenant_id"])

    op.create_table(
        "platform_deployment_revision",
        sa.Column("deployment_revision_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column(
            "deployment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_deployment.deployment_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_agent_version.agent_version_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("overrides", postgresql.JSONB(), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "deployment_id", "revision_number", name="uq_platform_deployment_revision_number"
        ),
    )
    op.create_index("ix_platform_deployment_revision_tenant_id", "platform_deployment_revision", ["tenant_id"])
    op.create_index(
        "ix_platform_deployment_revision_tenant_deployment",
        "platform_deployment_revision",
        ["tenant_id", "deployment_id"],
    )

    for table in TENANT_TABLES:
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        op.execute(
            sa.text(
                f"""CREATE POLICY {table}_tenant_isolation ON {table}
                USING (tenant_id = current_setting('app.tenant_id', true))
                WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"""
            )
        )


def downgrade() -> None:
    for table in reversed(TENANT_TABLES):
        op.drop_table(table)