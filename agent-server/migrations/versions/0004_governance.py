"""Create platform-native resource grants and audit events.

Revision ID: 0004_governance
Revises: 0003_control_plane
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004_governance"
down_revision: Union[str, None] = "0003_control_plane"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TENANT_TABLES = ("platform_resource_grant", "platform_audit_event")


def upgrade() -> None:
    op.create_table(
        "platform_resource_grant",
        sa.Column("grant_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("subject_type", sa.String(16), nullable=False),
        sa.Column("subject_id", sa.String(128), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(128), nullable=False),
        sa.Column("actions", postgresql.JSONB(), nullable=False),
        sa.Column("effect", sa.String(16), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_platform_resource_grant_tenant_id", "platform_resource_grant", ["tenant_id"])
    op.create_index(
        "ix_platform_resource_grant_lookup",
        "platform_resource_grant",
        ["tenant_id", "resource_type", "resource_id"],
    )

    op.create_table(
        "platform_audit_event",
        sa.Column("audit_event_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("actor_id", sa.String(128), nullable=False),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(128), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_platform_audit_event_tenant_id", "platform_audit_event", ["tenant_id"])
    op.create_index("ix_platform_audit_event_tenant_time", "platform_audit_event", ["tenant_id", "occurred_at"])

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