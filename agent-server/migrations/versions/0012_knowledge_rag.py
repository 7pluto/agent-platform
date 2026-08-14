"""Add knowledge documents, index versions and pgvector chunks.

Revision ID: 0012_knowledge_rag
Revises: 0011_run_scheduler_queue
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

revision = "0012_knowledge_rag"
down_revision = "0011_run_scheduler_queue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "platform_knowledge_document",
        sa.Column("document_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("knowledge_resource_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(256), nullable=False),
        sa.Column("object_key", sa.String(512), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "platform_knowledge_index_version",
        sa.Column("index_version_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("knowledge_resource_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("embedding_model", sa.String(128), nullable=False),
        sa.Column("chunk_strategy", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "knowledge_resource_version_id", "version_number", name="uq_platform_kb_index_version"),
    )
    op.create_table(
        "platform_knowledge_chunk",
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("index_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("platform_knowledge_index_version.index_version_id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("platform_knowledge_document.document_id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_number", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=False),
    )
    for table in ("platform_knowledge_document", "platform_knowledge_index_version", "platform_knowledge_chunk"):
        op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"CREATE POLICY {table}_tenant_isolation ON {table} USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"))


def downgrade() -> None:
    op.drop_table("platform_knowledge_chunk")
    op.drop_table("platform_knowledge_index_version")
    op.drop_table("platform_knowledge_document")
