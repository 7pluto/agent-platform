"""Bind conversations to deployments and add workbench idempotency.

Revision ID: 0017_conversation_workbench
Revises: 0016_secret_vault
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0017_conversation_workbench"
down_revision = "0016_secret_vault"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("platform_conversation", sa.Column("deployment_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index("ix_platform_conversation_deployment_id", "platform_conversation", ["deployment_id"])
    op.execute(sa.text("""
        WITH resolved AS (
            -- PostgreSQL has no min(uuid); uniqueness is established by HAVING,
            -- so the first value from the UUID aggregate is deterministic enough.
            SELECT conversation_id, (array_agg(deployment_id))[1] AS deployment_id
            FROM platform_run
            WHERE conversation_id IS NOT NULL
            GROUP BY conversation_id
            HAVING count(DISTINCT deployment_id) = 1
        )
        UPDATE platform_conversation c
        SET deployment_id = resolved.deployment_id
        FROM resolved
        WHERE c.conversation_id = resolved.conversation_id
    """))

    op.add_column("platform_conversation_message", sa.Column("source_run_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_unique_constraint("uq_platform_conversation_message_run_role", "platform_conversation_message", ["tenant_id", "thread_id", "source_run_id", "role"])
    op.create_unique_constraint("uq_platform_memory_source_run", "platform_memory_item", ["tenant_id", "deployment_id", "user_id", "source_run_id"])

    op.create_table(
        "platform_deployment_publish_idempotency",
        sa.Column("record_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("deployment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(256), nullable=False),
        sa.Column("response", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "user_id", "deployment_id", "idempotency_key", name="uq_platform_deployment_publish_idempotency"),
    )
    op.create_index("ix_platform_deployment_publish_idempotency_tenant_id", "platform_deployment_publish_idempotency", ["tenant_id"])
    op.execute(sa.text("ALTER TABLE platform_deployment_publish_idempotency ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE platform_deployment_publish_idempotency FORCE ROW LEVEL SECURITY"))
    op.execute(sa.text("CREATE POLICY platform_deployment_publish_idempotency_tenant_isolation ON platform_deployment_publish_idempotency USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"))


def downgrade() -> None:
    op.drop_table("platform_deployment_publish_idempotency")
    op.drop_constraint("uq_platform_memory_source_run", "platform_memory_item", type_="unique")
    op.drop_constraint("uq_platform_conversation_message_run_role", "platform_conversation_message", type_="unique")
    op.drop_column("platform_conversation_message", "source_run_id")
    op.drop_index("ix_platform_conversation_deployment_id", table_name="platform_conversation")
    op.drop_column("platform_conversation", "deployment_id")
