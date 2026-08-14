"""Create model definition and version resources.

Revision ID: 0007_model_resources
Revises: 0006_conversations
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0007_model_resources"
down_revision: Union[str, None] = "0006_conversations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table("platform_model_definition", sa.Column("model_id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("tenant_id", sa.String(128), nullable=False), sa.Column("slug", sa.String(64), nullable=False), sa.Column("display_name", sa.String(128), nullable=False), sa.Column("provider", sa.String(64), nullable=False), sa.Column("config", postgresql.JSONB(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.UniqueConstraint("tenant_id", "slug", name="uq_platform_model_definition_slug"))
    op.create_table("platform_model_version", sa.Column("model_version_id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("model_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("platform_model_definition.model_id", ondelete="CASCADE"), nullable=False), sa.Column("tenant_id", sa.String(128), nullable=False), sa.Column("version_number", sa.Integer(), nullable=False), sa.Column("status", sa.String(32), nullable=False), sa.Column("provider", sa.String(64), nullable=False), sa.Column("config", postgresql.JSONB(), nullable=False), sa.Column("content_hash", sa.String(64), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("published_at", sa.DateTime(timezone=True)), sa.UniqueConstraint("tenant_id", "model_id", "version_number", name="uq_platform_model_version_number"))
    for table in ("platform_model_definition", "platform_model_version"):
        op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"CREATE POLICY {table}_tenant_isolation ON {table} USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"))


def downgrade() -> None:
    op.drop_table("platform_model_version")
    op.drop_table("platform_model_definition")