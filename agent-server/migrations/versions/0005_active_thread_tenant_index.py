"""Scope active thread uniqueness by tenant.

Revision ID: 0005_active_thread_tenant_index
Revises: 0004_governance
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005_active_thread_tenant_index"
down_revision: Union[str, None] = "0004_governance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_INDEX = "uq_platform_run_active_thread"
_WHERE = sa.text("status IN ('RUNNING', 'CANCEL_REQUESTED')")


def upgrade() -> None:
    op.drop_index(_INDEX, table_name="platform_run")
    op.create_index(
        _INDEX,
        "platform_run",
        ["tenant_id", "thread_id"],
        unique=True,
        postgresql_where=_WHERE,
    )


def downgrade() -> None:
    op.drop_index(_INDEX, table_name="platform_run")
    op.create_index(
        _INDEX,
        "platform_run",
        ["thread_id"],
        unique=True,
        postgresql_where=_WHERE,
    )