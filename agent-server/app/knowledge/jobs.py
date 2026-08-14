from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select

from app.db.models import IngestJobRow
from app.db.rls import set_local_tenant_context
from app.db.session import get_session_factory
from app.iam.models import Principal
from app.knowledge.models import IngestJobRecord


class IngestJobStore:
    async def enqueue(self, tenant_id: str, user_id: str, knowledge_resource_version_id: UUID) -> IngestJobRow:
        async with get_session_factory()() as session:
            async with session.begin():
                row = IngestJobRow(job_id=uuid4(), tenant_id=tenant_id, user_id=user_id, knowledge_resource_version_id=knowledge_resource_version_id, status="PENDING")
                session.add(row)
                await session.flush()
                return row

    async def claim(self, worker_id: str) -> IngestJobRow | None:
        async with get_session_factory()() as session:
            async with session.begin():
                row = await session.scalar(select(IngestJobRow).where(IngestJobRow.status == "PENDING").order_by(IngestJobRow.created_at).with_for_update(skip_locked=True))
                if row is None:
                    return None
                row.status = "RUNNING"; row.claimed_by = worker_id
                return row

    async def finish(self, job_id: UUID, error_code: str | None = None) -> None:
        async with get_session_factory()() as session:
            async with session.begin():
                row = await session.get(IngestJobRow, job_id)
                if row:
                    row.status = "FAILED" if error_code else "COMPLETED"
                    row.error_code = error_code; row.completed_at = datetime.now(timezone.utc)

    async def list_for_knowledge(
        self, principal: Principal, knowledge_resource_version_id: UUID
    ) -> list[IngestJobRecord]:
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                rows = await session.scalars(
                    select(IngestJobRow)
                    .where(
                        IngestJobRow.tenant_id == principal.tenant_id,
                        IngestJobRow.knowledge_resource_version_id == knowledge_resource_version_id,
                    )
                    .order_by(IngestJobRow.created_at.desc())
                )
                return [
                    IngestJobRecord(
                        job_id=row.job_id,
                        knowledge_resource_version_id=row.knowledge_resource_version_id,
                        status=row.status,
                        error_code=row.error_code,
                        created_at=row.created_at,
                        completed_at=row.completed_at,
                    )
                    for row in rows.all()
                ]


ingest_jobs = IngestJobStore()
