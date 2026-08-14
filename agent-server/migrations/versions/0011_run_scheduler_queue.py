"""Add minimal cross-tenant scheduler queue.

Revision ID: 0011_run_scheduler_queue
Revises: 0010_memory_items
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011_run_scheduler_queue"
down_revision = "0010_memory_items"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_run_scheduler_queue",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("platform_run.run_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("attempt", sa.Integer(), server_default="0", nullable=False),
        sa.Column("claimed_by", sa.String(128)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_platform_scheduler_queue_available", "platform_run_scheduler_queue", ["available_at", "run_id"])
    # This is intentionally not an RLS data table: it contains only scheduler
    # identity fields, never messages, manifests, prompts or resource content.


def downgrade() -> None:
    op.drop_table("platform_run_scheduler_queue")
