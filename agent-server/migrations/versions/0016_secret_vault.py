"""Add encrypted tenant secret vault.

Revision ID: 0016_secret_vault
Revises: 0015_grant_action_constraint
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0016_secret_vault"
down_revision = "0015_grant_action_constraint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_secret_vault",
        sa.Column("secret_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_platform_secret_vault_tenant", "platform_secret_vault", ["tenant_id"])
    op.execute(sa.text("ALTER TABLE platform_secret_vault ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE platform_secret_vault FORCE ROW LEVEL SECURITY"))
    op.execute(sa.text("CREATE POLICY platform_secret_vault_tenant_isolation ON platform_secret_vault USING (tenant_id = current_setting('app.tenant_id', true)) WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"))


def downgrade() -> None:
    op.drop_table("platform_secret_vault")
