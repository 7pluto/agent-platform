from __future__ import annotations

from uuid import UUID, uuid4

from datetime import datetime, timezone

from sqlalchemy import func, select

from app.core.errors import ApiError
from app.db.models import MemoryItemRow
from app.db.rls import set_local_tenant_context
from app.db.session import get_session_factory
from app.iam.models import Principal
from app.memory.models import MemoryCreate, MemoryItem


class MemoryStore:
    async def create(self, request: MemoryCreate, principal: Principal, max_items: int) -> MemoryItem:
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                active_count = await session.scalar(
                    select(func.count(MemoryItemRow.memory_id)).where(
                        MemoryItemRow.tenant_id == principal.tenant_id,
                        MemoryItemRow.deployment_id == request.deployment_id,
                        MemoryItemRow.user_id == principal.external_user_id,
                        (MemoryItemRow.expires_at.is_(None)) | (MemoryItemRow.expires_at > datetime.now(timezone.utc)),
                    )
                )
                if request.source_run_id is not None:
                    existing = await session.scalar(
                        select(MemoryItemRow).where(
                            MemoryItemRow.tenant_id == principal.tenant_id,
                            MemoryItemRow.deployment_id == request.deployment_id,
                            MemoryItemRow.user_id == principal.external_user_id,
                            MemoryItemRow.source_run_id == request.source_run_id,
                        )
                    )
                    if existing is not None:
                        return self._item(existing)
                if (active_count or 0) >= max_items:
                    raise ApiError(409, "MEMORY_LIMIT_REACHED", "active Memory items reached the policy limit")
                row = MemoryItemRow(memory_id=uuid4(), tenant_id=principal.tenant_id, deployment_id=request.deployment_id, user_id=principal.external_user_id, category=request.category, content=request.content, source_run_id=request.source_run_id, expires_at=request.expires_at)
                session.add(row)
                await session.flush()
                return self._item(row)

    async def list_mine(self, deployment_id: UUID, principal: Principal) -> list[MemoryItem]:
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                rows = await session.scalars(select(MemoryItemRow).where(MemoryItemRow.tenant_id == principal.tenant_id, MemoryItemRow.deployment_id == deployment_id, MemoryItemRow.user_id == principal.external_user_id).order_by(MemoryItemRow.created_at.desc()))
                return [self._item(row) for row in rows.all()]

    async def delete_mine(self, memory_id: UUID, principal: Principal) -> None:
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                row = await session.get(MemoryItemRow, memory_id)
                if row is None or row.user_id != principal.external_user_id:
                    return
                await session.delete(row)

    async def list_for_runtime(self, tenant_id: str, deployment_id: UUID, user_id: str, limit: int = 20) -> list[MemoryItem]:
        """Read only the current user's deployment-scoped non-expired memory."""
        from datetime import datetime, timezone

        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, tenant_id, user_id)
                rows = await session.scalars(
                    select(MemoryItemRow)
                    .where(
                        MemoryItemRow.tenant_id == tenant_id,
                        MemoryItemRow.deployment_id == deployment_id,
                        MemoryItemRow.user_id == user_id,
                        (MemoryItemRow.expires_at.is_(None)) | (MemoryItemRow.expires_at > datetime.now(timezone.utc)),
                    )
                    .order_by(MemoryItemRow.created_at.desc())
                    .limit(limit)
                )
                return [self._item(row) for row in rows.all()]

    @staticmethod
    def _item(row: MemoryItemRow) -> MemoryItem:
        return MemoryItem(memory_id=row.memory_id, tenant_id=row.tenant_id, deployment_id=row.deployment_id, user_id=row.user_id, category=row.category, content=row.content, source_run_id=row.source_run_id, expires_at=row.expires_at, created_at=row.created_at)
