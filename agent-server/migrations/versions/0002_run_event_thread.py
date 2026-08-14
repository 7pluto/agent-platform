"""Add thread identity to persisted Run Events.

Revision ID: 0002_run_event_thread
Revises: 0001_core
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002_run_event_thread"
down_revision: Union[str, None] = "0001_core"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Backfill thread identity for databases created by the original 0001 schema.

    Current 0001_core already contains ``thread_id``.  Keep this revision
    conditional so a fresh database and an older deployed schema both upgrade.
    """
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("platform_run_event")}
    if "thread_id" in columns:
        return

    op.add_column(
        "platform_run_event",
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(sa.text("ALTER TABLE platform_run_event NO FORCE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            """UPDATE platform_run_event AS event
            SET thread_id = run.thread_id
            FROM platform_run AS run
            WHERE run.run_id = event.run_id"""
        )
    )
    op.alter_column("platform_run_event", "thread_id", nullable=False)
    op.execute(sa.text("ALTER TABLE platform_run_event FORCE ROW LEVEL SECURITY"))


def downgrade() -> None:
    # 0001_core now owns this column; dropping it would corrupt a fresh schema.
    pass