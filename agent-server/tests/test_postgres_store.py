import asyncio
from uuid import uuid4

from app.core.errors import ApiError
from app.db.models import RunEventRow

from app.runtime.manifest import build_execution_manifest
from app.runtime.models import RunEvent, RunRecord
from app.runtime.postgres_store import PostgresRunStore


def _record() -> RunRecord:
    record = RunRecord(
        tenant_id="tenant-a",
        user_id="user-a",
        deployment_id=uuid4(),
        thread_id=uuid4(),
        message="persist me",
    )
    record.execution_manifest = build_execution_manifest(record)
    return record


def test_postgres_row_conversion_preserves_manifest_and_thread() -> None:
    record = _record()
    row = PostgresRunStore._to_row(record)
    restored = PostgresRunStore._to_record(row)
    assert restored.run_id == record.run_id
    assert restored.thread_id == record.thread_id
    assert restored.execution_manifest is not None
    assert restored.execution_manifest.manifest_hash == record.execution_manifest.manifest_hash


def test_postgres_event_conversion_preserves_thread() -> None:
    record = _record()
    row = RunEventRow(
        run_id=record.run_id,
        sequence=1,
        event_id=uuid4(),
        thread_id=record.thread_id,
        event="run.started",
        trace_id=f"run-{record.run_id.hex}",
        data={},
        tenant_id=record.tenant_id,
    )
    event = PostgresRunStore._to_event(row)
    assert isinstance(event, RunEvent)
    assert event.thread_id == record.thread_id


def test_persisted_finish_requires_tenant_context() -> None:
    async def run() -> None:
        try:
            await PostgresRunStore().finish(uuid4())
        except ApiError as exc:
            assert exc.code == "TENANT_CONTEXT_REQUIRED"
        else:
            raise AssertionError("persisted finish accepted missing tenant context")

    asyncio.run(run())