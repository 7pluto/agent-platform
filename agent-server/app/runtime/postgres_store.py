from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.config import get_settings
from app.db.models import RunEventRow, RunIdempotencyRow, RunRow, RunSchedulerQueueRow, ThreadLeaseRow
from app.db.rls import set_local_tenant_context
from app.db.session import dispose_engine, get_session_factory
from app.iam.models import Principal
from app.runtime.manifest import build_execution_manifest
from app.runtime.models import ExecutionManifest, RunCreateRequest, RunEvent, RunRecord, RunStatus


_ACTIVE = {RunStatus.RUNNING.value, RunStatus.CANCEL_REQUESTED.value}
_TERMINAL = {RunStatus.COMPLETED.value, RunStatus.FAILED.value, RunStatus.CANCELLED.value}


class PostgresRunStore:
    """PostgreSQL implementation of the RunStore contract.

    Every public operation opens a transaction and sets the RLS context before
    reading or writing tenant data. The in-memory store remains the dev default.
    """

    async def create(
        self,
        request: RunCreateRequest,
        principal: Principal,
        idempotency_key: str,
        manifest_builder: Callable[[RunRecord], ExecutionManifest] | None = None,
    ) -> RunRecord:
        self._validate_request(request, principal)
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                existing = await session.scalar(
                    select(RunIdempotencyRow).where(
                        RunIdempotencyRow.tenant_id == principal.tenant_id,
                        RunIdempotencyRow.user_id == principal.external_user_id,
                        RunIdempotencyRow.deployment_id == request.deployment_id,
                        RunIdempotencyRow.idempotency_key == idempotency_key,
                    )
                )
                if existing:
                    row = await session.get(RunRow, existing.run_id)
                    if row is None:
                        raise ApiError(409, "IDEMPOTENCY_CORRUPT", "idempotency record has no Run")
                    return self._to_record(row)

                record = RunRecord(
                    tenant_id=principal.tenant_id,
                    user_id=principal.external_user_id,
                    deployment_id=request.deployment_id,
                    thread_id=request.thread_id or uuid4(),
                    conversation_id=request.conversation_id,
                    message=request.message,
                )
                record.execution_manifest = (
                    manifest_builder(record) if manifest_builder else build_execution_manifest(record)
                )
                row = self._to_row(record)
                lease = await self._lock_lease(session, record.tenant_id, record.thread_id)
                active = await self._active_run(session, lease)
                run_in_worker = get_settings().runtime_execution_mode == "worker"
                if active is None and not run_in_worker:
                    row.status = RunStatus.RUNNING.value
                session.add(row)
                await session.flush()
                if lease is None:
                    lease = ThreadLeaseRow(tenant_id=record.tenant_id, thread_id=record.thread_id)
                    session.add(lease)
                    await session.flush()
                if active is None and not run_in_worker:
                    lease.active_run_id = record.run_id
                session.add(
                    RunIdempotencyRow(
                        tenant_id=record.tenant_id,
                        user_id=record.user_id,
                        deployment_id=record.deployment_id,
                        idempotency_key=idempotency_key,
                        run_id=record.run_id,
                    )
                )
                if run_in_worker:
                    session.add(RunSchedulerQueueRow(run_id=record.run_id, tenant_id=record.tenant_id, user_id=record.user_id, thread_id=record.thread_id))
                await self._append_event(session, row, "run.created", {})
                await self._append_event(
                    session,
                    row,
                    "manifest.created",
                    {"manifest_hash": record.execution_manifest.manifest_hash},
                )
                if active is None and not run_in_worker:
                    await self._append_event(
                        session,
                        row,
                        "run.started",
                        {"trace_id": self._trace_id(record)},
                    )
                return self._to_record(row)

    async def get(self, run_id: UUID, principal: Principal) -> RunRecord:
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                row = await session.get(RunRow, run_id)
                self._check_owner(row, principal)
                return self._to_record(row)

    async def list_for_principal(self, principal: Principal, limit: int = 50) -> list[RunRecord]:
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                rows = await session.scalars(
                    select(RunRow)
                    .where(RunRow.tenant_id == principal.tenant_id, RunRow.user_id == principal.external_user_id)
                    .order_by(RunRow.created_at.desc())
                    .limit(limit)
                )
                return [self._to_record(row) for row in rows.all()]

    async def list_for_tenant(self, principal: Principal, limit: int = 500) -> list[RunRecord]:
        """Tenant-scoped administrative listing; caller enforces administrator role."""
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                rows = await session.scalars(
                    select(RunRow)
                    .where(RunRow.tenant_id == principal.tenant_id)
                    .order_by(RunRow.created_at.desc())
                    .limit(limit)
                )
                return [self._to_record(row) for row in rows.all()]

    async def claim_next_for_worker(self, worker_id: str) -> RunRecord | None:
        """Claim only a queue row, then switch immediately to a tenant transaction.

        The query deliberately selects no message, manifest or resource fields
        until the tenant has been established from the claimed row.
        """
        async with get_session_factory()() as session:
            async with session.begin():
                # Queue rows are the only scheduler-visible cross-tenant data.
                # No Run, message, manifest or resource data is selected here.
                claimed = await session.execute(text("""
                    SELECT run_id, tenant_id, user_id
                    FROM platform_run_scheduler_queue
                    WHERE available_at <= now()
                      AND (lease_expires_at IS NULL OR lease_expires_at < now())
                    ORDER BY available_at, run_id
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                """))
                row = claimed.mappings().first()
                if row is None:
                    return None
                await session.execute(text("""
                    UPDATE platform_run_scheduler_queue
                    SET claimed_by = :worker_id,
                        attempt = attempt + 1,
                        heartbeat_at = now(),
                        lease_expires_at = now() + interval '5 minutes'
                    WHERE run_id = :run_id
                """), {"worker_id": worker_id, "run_id": row["run_id"]})
                await set_local_tenant_context(session, row["tenant_id"], row["user_id"])
                run = await session.scalar(select(RunRow).where(RunRow.run_id == row["run_id"], RunRow.status == RunStatus.PENDING.value).with_for_update())
                if run is None:
                    return None
                lease = await self._lock_lease(session, run.tenant_id, run.thread_id)
                if lease is not None and lease.active_run_id is not None:
                    # Keep this scheduler record pending. It contains no run
                    # body and will become eligible once the active lease ends.
                    await session.execute(text("""
                        UPDATE platform_run_scheduler_queue
                        SET claimed_by = NULL, lease_expires_at = NULL,
                            available_at = now() + interval '1 second'
                        WHERE run_id = :run_id
                    """), {"run_id": run.run_id})
                    return None
                run.status = RunStatus.RUNNING.value
                if lease is None:
                    lease = ThreadLeaseRow(tenant_id=run.tenant_id, thread_id=run.thread_id)
                    session.add(lease)
                lease.active_run_id = run.run_id
                await self._append_event(session, run, "run.claimed", {"worker_id": worker_id})
                await self._append_event(session, run, "run.started", {"trace_id": self._trace_id(self._to_record(run))})
                return self._to_record(run)

    async def events(self, run_id: UUID, principal: Principal, after: int = 0) -> list[RunEvent]:
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                row = await session.get(RunRow, run_id)
                self._check_owner(row, principal)
                result = await session.scalars(
                    select(RunEventRow)
                    .where(RunEventRow.run_id == run_id, RunEventRow.sequence > after)
                    .order_by(RunEventRow.sequence)
                )
                return [self._to_event(item) for item in result.all()]

    async def events_for_tenant(self, run_id: UUID, principal: Principal) -> list[RunEvent]:
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                row = await session.get(RunRow, run_id)
                if row is None or row.tenant_id != principal.tenant_id:
                    raise ApiError(404, "NOT_FOUND", "run was not found")
                result = await session.scalars(
                    select(RunEventRow).where(RunEventRow.run_id == run_id).order_by(RunEventRow.sequence)
                )
                return [self._to_event(item) for item in result.all()]

    async def cancel(self, run_id: UUID, principal: Principal) -> RunRecord:
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                row = await session.scalar(select(RunRow).where(RunRow.run_id == run_id).with_for_update())
                self._check_owner(row, principal)
                if row.status in _TERMINAL:
                    return self._to_record(row)
                lease = await self._lock_lease(session, row.tenant_id, row.thread_id)
                if row.status == RunStatus.PENDING.value:
                    row.status = RunStatus.CANCELLED.value
                    await self._append_event(session, row, "run.cancelled", {"reason": "user_request"})
                else:
                    row.status = RunStatus.CANCEL_REQUESTED.value
                    await self._append_event(session, row, "run.cancel_requested", {})
                    row.status = RunStatus.CANCELLED.value
                    await self._append_event(session, row, "run.cancelled", {"reason": "user_request"})
                    if lease and lease.active_run_id == row.run_id:
                        lease.active_run_id = None
                if lease:
                    await self._promote_next(session, lease)
                await session.execute(text("DELETE FROM platform_run_scheduler_queue WHERE run_id = :run_id"), {"run_id": run_id})
                return self._to_record(row)

    async def finish(
        self,
        run_id: UUID,
        status: RunStatus = RunStatus.COMPLETED,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> RunRecord:
        if not tenant_id:
            raise ApiError(500, "TENANT_CONTEXT_REQUIRED", "tenant_id is required to finish a persisted Run")
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, tenant_id, user_id or "worker")
                row = await session.scalar(select(RunRow).where(RunRow.run_id == run_id).with_for_update())
                if row is None:
                    raise ApiError(404, "NOT_FOUND", "run was not found")
                if row.status in (RunStatus.RUNNING.value, RunStatus.CANCEL_REQUESTED.value):
                    row.status = status.value
                    lease = await self._lock_lease(session, row.tenant_id, row.thread_id)
                    if lease and lease.active_run_id == row.run_id:
                        lease.active_run_id = None
                    await self._append_event(session, row, f"run.{status.value.lower()}", {})
                    if lease:
                        await self._promote_next(session, lease)
                    await session.execute(text("DELETE FROM platform_run_scheduler_queue WHERE run_id = :run_id"), {"run_id": run_id})
                return self._to_record(row)

    async def append_runtime_event(
        self,
        run_id: UUID,
        event: str,
        data: dict,
        tenant_id: str,
        user_id: str,
    ) -> None:
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, tenant_id, user_id)
                row = await session.scalar(select(RunRow).where(RunRow.run_id == run_id).with_for_update())
                self._check_worker_owner(row, tenant_id, user_id)
                await self._append_event(session, row, event, data)

    async def is_cancelled(self, run_id: UUID, tenant_id: str, user_id: str) -> bool:
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, tenant_id, user_id)
                row = await session.get(RunRow, run_id)
                self._check_worker_owner(row, tenant_id, user_id)
                return row.status in (RunStatus.CANCEL_REQUESTED.value, RunStatus.CANCELLED.value)

    async def active_for_thread(self, thread_id: UUID, tenant_id: str, user_id: str) -> RunRecord | None:
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, tenant_id, user_id)
                lease = await session.get(ThreadLeaseRow, (tenant_id, thread_id))
                if lease is None or lease.active_run_id is None:
                    return None
                row = await session.get(RunRow, lease.active_run_id)
                self._check_worker_owner(row, tenant_id, user_id)
                return self._to_record(row)

    async def close(self) -> None:
        await dispose_engine()

    @staticmethod
    def _validate_request(request: RunCreateRequest, principal: Principal) -> None:
        if request.user_id and request.user_id != principal.external_user_id:
            raise ApiError(403, "FORBIDDEN", "request user_id does not match the authenticated principal")
        if request.tenant_id and request.tenant_id != principal.tenant_id:
            raise ApiError(403, "TENANT_FORBIDDEN", "request tenant_id does not match the authenticated tenant")

    @staticmethod
    def _to_row(record: RunRecord) -> RunRow:
        if record.execution_manifest is None:
            raise ApiError(409, "MANIFEST_UNAVAILABLE", "run has no execution manifest")
        return RunRow(
            run_id=record.run_id,
            tenant_id=record.tenant_id,
            user_id=record.user_id,
            deployment_id=record.deployment_id,
            thread_id=record.thread_id,
            conversation_id=record.conversation_id,
            message=record.message,
            status=RunStatus.PENDING.value,
            execution_manifest=record.execution_manifest.model_dump(mode="json"),
            created_at=record.created_at,
        )

    @staticmethod
    def _to_record(row: RunRow) -> RunRecord:
        from app.runtime.models import ExecutionManifest

        return RunRecord(
            run_id=row.run_id,
            tenant_id=row.tenant_id,
            user_id=row.user_id,
            deployment_id=row.deployment_id,
            thread_id=row.thread_id,
            conversation_id=row.conversation_id,
            message=row.message,
            status=RunStatus(row.status),
            created_at=row.created_at or datetime.now(timezone.utc),
            execution_manifest=ExecutionManifest.model_validate(row.execution_manifest),
        )

    @staticmethod
    def _to_event(row: RunEventRow) -> RunEvent:
        return RunEvent(
            sequence=row.sequence,
            event_id=row.event_id,
            event=row.event,
            run_id=row.run_id,
            thread_id=row.thread_id,
            trace_id=row.trace_id,
            occurred_at=row.occurred_at or datetime.now(timezone.utc),
            data=row.data,
        )

    @staticmethod
    async def _lock_lease(session: AsyncSession, tenant_id: str, thread_id: UUID) -> ThreadLeaseRow | None:
        return await session.scalar(
            select(ThreadLeaseRow)
            .where(ThreadLeaseRow.tenant_id == tenant_id, ThreadLeaseRow.thread_id == thread_id)
            .with_for_update()
        )

    @staticmethod
    async def _active_run(session: AsyncSession, lease: ThreadLeaseRow | None) -> RunRow | None:
        if lease is None or lease.active_run_id is None:
            return None
        row = await session.get(RunRow, lease.active_run_id)
        if row is None or row.status not in _ACTIVE:
            lease.active_run_id = None
            return None
        return row

    async def _promote_next(self, session: AsyncSession, lease: ThreadLeaseRow) -> None:
        if lease.active_run_id is not None:
            return
        if get_settings().runtime_execution_mode == "worker":
            # PENDING rows already have queue entries. The scheduler will claim
            # the next one after this transaction releases the Thread lease.
            return
        pending = await session.scalar(
            select(RunRow)
            .where(RunRow.tenant_id == lease.tenant_id, RunRow.thread_id == lease.thread_id)
            .where(RunRow.status == RunStatus.PENDING.value)
            .order_by(RunRow.created_at, RunRow.run_id)
            .with_for_update()
        )
        if pending is None:
            return
        pending.status = RunStatus.RUNNING.value
        lease.active_run_id = pending.run_id
        await self._append_event(
            session,
            pending,
            "run.started",
            {"trace_id": self._trace_id(self._to_record(pending))},
        )

    @staticmethod
    async def _append_event(session: AsyncSession, row: RunRow, event: str, data: dict) -> None:
        max_sequence = await session.scalar(
            select(func.max(RunEventRow.sequence)).where(RunEventRow.run_id == row.run_id)
        )
        session.add(
            RunEventRow(
                run_id=row.run_id,
                sequence=(max_sequence or 0) + 1,
                event_id=uuid4(),
                event=event,
                thread_id=row.thread_id,
                trace_id=f"run-{row.run_id.hex}",
                data=data,
                tenant_id=row.tenant_id,
            )
        )

    @staticmethod
    def _trace_id(record: RunRecord) -> str:
        return f"run-{record.run_id.hex}"

    @staticmethod
    def _check_worker_owner(row: RunRow | None, tenant_id: str, user_id: str) -> None:
        if row is None or row.tenant_id != tenant_id or row.user_id != user_id:
            raise ApiError(404, "NOT_FOUND", "run was not found")

    @staticmethod
    def _check_owner(row: RunRow | None, principal: Principal) -> None:
        if row is None or row.tenant_id != principal.tenant_id or row.user_id != principal.external_user_id:
            raise ApiError(404, "NOT_FOUND", "run was not found")
