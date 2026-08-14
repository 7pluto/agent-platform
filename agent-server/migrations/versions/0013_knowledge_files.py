"""Persist uploaded knowledge-file metadata.

Revision ID: 0013_knowledge_files
Revises: 0012_knowledge_rag
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0013_knowledge_files"
down_revision = "0012_knowledge_rag"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_knowledge_file",
        sa.Column("file_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("filename", sa.String(256), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("object_key", sa.String(512), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_platform_knowledge_file_tenant_id", "platform_knowledge_file", ["tenant_id"])
    op.execute(sa.text("ALTER TABLE platform_knowledge_file ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE platform_knowledge_file FORCE ROW LEVEL SECURITY"))
    op.execute(sa.text("CREATE POLICY platform_knowledge_file_tenant_isolation ON platform_knowledge_file USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"))


def downgrade() -> None:
    op.drop_table("platform_knowledge_file")
