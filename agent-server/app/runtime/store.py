from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Callable
from uuid import UUID, uuid4

from app.core.errors import ApiError
from app.iam.models import Principal
from app.runtime.manifest import build_execution_manifest
from app.runtime.models import ExecutionManifest, RunCreateRequest, RunEvent, RunRecord, RunStatus


class RunStore:
    """Phase-1 in-memory implementation of the Thread lease rules."""

    def __init__(self) -> None:
        self._runs: dict[UUID, RunRecord] = {}
        self._events: dict[UUID, list[RunEvent]] = defaultdict(list)
        self._active_by_thread: dict[tuple[str, UUID], UUID] = {}
        self._idempotency: dict[tuple[str, str, UUID, str], UUID] = {}
        self._lock = asyncio.Lock()

    async def create(
        self,
        request: RunCreateRequest,
        principal: Principal,
        idempotency_key: str,
        manifest_builder: Callable[[RunRecord], ExecutionManifest] | None = None,
    ) -> RunRecord:
        if request.user_id and request.user_id != principal.external_user_id:
            raise ApiError(403, "FORBIDDEN", "request user_id does not match the authenticated principal")
        if request.tenant_id and request.tenant_id != principal.tenant_id:
            raise ApiError(403, "TENANT_FORBIDDEN", "request tenant_id does not match the authenticated tenant")
        key = (principal.tenant_id, principal.external_user_id, request.deployment_id, idempotency_key)
        async with self._lock:
            existing_id = self._idempotency.get(key)
            if existing_id:
                return self._runs[existing_id].model_copy(deep=True)
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
            self._runs[record.run_id] = record
            self._idempotency[key] = record.run_id
            self._append(record, "run.created", {})
            self._append(record, "manifest.created", {"manifest_hash": record.execution_manifest.manifest_hash})
            self._claim_next_locked(record.tenant_id, record.thread_id)
            return record.model_copy(deep=True)

    async def get(self, run_id: UUID, principal: Principal) -> RunRecord:
        async with self._lock:
            record = self._runs.get(run_id)
            self._check_owner(record, principal)
            return record.model_copy(deep=True)

    async def list_for_principal(self, principal: Principal, limit: int = 50) -> list[RunRecord]:
        async with self._lock:
            return [
                record.model_copy(deep=True)
                for record in sorted(self._runs.values(), key=lambda item: item.created_at, reverse=True)
                if record.tenant_id == principal.tenant_id and record.user_id == principal.external_user_id
            ][:limit]

    async def list_for_tenant(self, principal: Principal, limit: int = 500) -> list[RunRecord]:
        """Administrative, tenant-only read used by observability summaries."""
        async with self._lock:
            return [
                record.model_copy(deep=True)
                for record in sorted(self._runs.values(), key=lambda item: item.created_at, reverse=True)
                if record.tenant_id == principal.tenant_id
            ][:limit]

    async def events(self, run_id: UUID, principal: Principal, after: int = 0) -> list[RunEvent]:
        async with self._lock:
            record = self._runs.get(run_id)
            self._check_owner(record, principal)
            return [event.model_copy(deep=True) for event in self._events[run_id] if event.sequence > after]

    async def events_for_tenant(self, run_id: UUID, principal: Principal) -> list[RunEvent]:
        async with self._lock:
            record = self._runs.get(run_id)
            if record is None or record.tenant_id != principal.tenant_id:
                raise ApiError(404, "NOT_FOUND", "run was not found")
            return [event.model_copy(deep=True) for event in self._events[run_id]]

    async def cancel(self, run_id: UUID, principal: Principal) -> RunRecord:
        async with self._lock:
            record = self._runs.get(run_id)
            self._check_owner(record, principal)
            if record.status in (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED):
                return record.model_copy(deep=True)
            if record.status == RunStatus.PENDING:
                record.status = RunStatus.CANCELLED
                self._append(record, "run.cancelled", {"reason": "user_request"})
                self._claim_next_locked(record.tenant_id, record.thread_id)
            else:
                record.status = RunStatus.CANCEL_REQUESTED
                self._append(record, "run.cancel_requested", {})
                record.status = RunStatus.CANCELLED
                self._active_by_thread.pop((record.tenant_id, record.thread_id), None)
                self._append(record, "run.cancelled", {"reason": "user_request"})
                self._claim_next_locked(record.tenant_id, record.thread_id)
            return record.model_copy(deep=True)

    async def finish(
        self,
        run_id: UUID,
        status: RunStatus = RunStatus.COMPLETED,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> RunRecord:
        async with self._lock:
            record = self._runs[run_id]
            if record.status in (RunStatus.RUNNING, RunStatus.CANCEL_REQUESTED):
                record.status = status
                self._active_by_thread.pop((record.tenant_id, record.thread_id), None)
                self._append(record, f"run.{status.value.lower()}", {})
                self._claim_next_locked(record.tenant_id, record.thread_id)
            return record.model_copy(deep=True)

    async def append_runtime_event(
        self,
        run_id: UUID,
        event: str,
        data: dict,
        tenant_id: str,
        user_id: str,
    ) -> None:
        async with self._lock:
            record = self._runs.get(run_id)
            self._check_worker_owner(record, tenant_id, user_id)
            self._append(record, event, data)

    async def is_cancelled(self, run_id: UUID, tenant_id: str, user_id: str) -> bool:
        async with self._lock:
            record = self._runs.get(run_id)
            self._check_worker_owner(record, tenant_id, user_id)
            return record.status in (RunStatus.CANCEL_REQUESTED, RunStatus.CANCELLED)

    async def active_for_thread(self, thread_id: UUID, tenant_id: str, user_id: str) -> RunRecord | None:
        async with self._lock:
            run_id = self._active_by_thread.get((tenant_id, thread_id))
            if run_id is None:
                return None
            record = self._runs.get(run_id)
            self._check_worker_owner(record, tenant_id, user_id)
            return record.model_copy(deep=True)

    def _claim_next_locked(self, tenant_id: str, thread_id: UUID) -> None:
        if (tenant_id, thread_id) in self._active_by_thread:
            return
        pending = sorted(
            (run for run in self._runs.values() if run.tenant_id == tenant_id and run.thread_id == thread_id and run.status == RunStatus.PENDING),
            key=lambda run: run.created_at,
        )
        if not pending:
            return
        record = pending[0]
        record.status = RunStatus.RUNNING
        self._active_by_thread[(tenant_id, thread_id)] = record.run_id
        self._append(record, "run.started", {"trace_id": self._trace_id(record)})

    def _append(self, record: RunRecord, event: str, data: dict) -> None:
        sequence = len(self._events[record.run_id]) + 1
        self._events[record.run_id].append(
            RunEvent(
                sequence=sequence,
                event=event,
                run_id=record.run_id,
                thread_id=record.thread_id,
                trace_id=self._trace_id(record),
                data=data,
            )
        )

    @staticmethod
    def _trace_id(record: RunRecord) -> str:
        return f"run-{record.run_id.hex}"

    @staticmethod
    def _check_worker_owner(record: RunRecord | None, tenant_id: str, user_id: str) -> None:
        if not record or record.tenant_id != tenant_id or record.user_id != user_id:
            raise ApiError(404, "NOT_FOUND", "run was not found")

    @staticmethod
    def _check_owner(record: RunRecord | None, principal: Principal) -> None:
        if not record or record.tenant_id != principal.tenant_id or record.user_id != principal.external_user_id:
            raise ApiError(404, "NOT_FOUND", "run was not found")
