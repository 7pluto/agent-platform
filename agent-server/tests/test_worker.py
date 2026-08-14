import asyncio
from uuid import uuid4

from app.iam.models import Principal
from app.runtime.models import RunCreateRequest, RunStatus
from app.runtime.store import RunStore
from app.runtime.worker import InProcessRuntimeWorker


def _principal() -> Principal:
    return Principal(
        provider="mock",
        external_user_id="user-demo",
        external_org_id="org-demo",
        tenant_id="tenant-demo",
        display_name="Demo User",
    )


def test_in_process_worker_completes_and_drains_thread_queue() -> None:
    async def run() -> None:
        store = RunStore()
        principal = _principal()
        thread_id = uuid4()
        deployment_id = uuid4()
        first = await store.create(
            RunCreateRequest(deployment_id=deployment_id, thread_id=thread_id, message="first"),
            principal,
            "worker-first",
        )
        second = await store.create(
            RunCreateRequest(deployment_id=deployment_id, thread_id=thread_id, message="second"),
            principal,
            "worker-second",
        )
        assert first.status == RunStatus.RUNNING
        assert second.status == RunStatus.PENDING

        worker = InProcessRuntimeWorker(store=store)
        worker.submit(first)
        for _ in range(20):
            result = await store.get(second.run_id, principal)
            if result.status == RunStatus.COMPLETED:
                break
            await asyncio.sleep(0)
        else:
            raise AssertionError("worker did not drain pending run")

        events = await store.events(second.run_id, principal)
        assert any(event.event == "runtime.output" for event in events)
        assert (await store.get(first.run_id, principal)).status == RunStatus.COMPLETED
        await worker.shutdown()

    asyncio.run(run())