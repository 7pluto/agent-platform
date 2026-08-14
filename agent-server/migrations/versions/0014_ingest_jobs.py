"""Add scheduler-visible minimal knowledge ingest jobs.

Revision ID: 0014_ingest_jobs
Revises: 0013_knowledge_files
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0014_ingest_jobs"
down_revision = "0013_knowledge_files"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_ingest_job",
        sa.Column("job_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("knowledge_resource_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("claimed_by", sa.String(128)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_platform_ingest_job_queue", "platform_ingest_job", ["status", "created_at"])
    # Scheduler table carries only stable identifiers; document content stays
    # behind tenant RLS in the knowledge tables.


def downgrade() -> None:
    op.drop_table("platform_ingest_job")
