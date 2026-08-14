"""Create tenant-scoped conversation storage.

Revision ID: 0006_conversations
Revises: 0005_active_thread_tenant_index
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0006_conversations"
down_revision: Union[str, None] = "0005_active_thread_tenant_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("platform_conversation", "platform_conversation_thread", "platform_conversation_message")


def upgrade() -> None:
    op.create_table("platform_conversation", sa.Column("conversation_id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("tenant_id", sa.String(128), nullable=False), sa.Column("user_id", sa.String(128), nullable=False), sa.Column("title", sa.String(256)), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_table("platform_conversation_thread", sa.Column("thread_id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("conversation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("platform_conversation.conversation_id", ondelete="CASCADE"), nullable=False), sa.Column("tenant_id", sa.String(128), nullable=False), sa.Column("user_id", sa.String(128), nullable=False), sa.Column("title", sa.String(256)), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_table("platform_conversation_message", sa.Column("message_id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("thread_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("platform_conversation_thread.thread_id", ondelete="CASCADE"), nullable=False), sa.Column("tenant_id", sa.String(128), nullable=False), sa.Column("user_id", sa.String(128), nullable=False), sa.Column("role", sa.String(16), nullable=False), sa.Column("content", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    for table in _TABLES:
        op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"CREATE POLICY {table}_tenant_isolation ON {table} USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"))


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_table(table)