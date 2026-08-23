from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.config import get_settings
from app.runtime.adapter import RuntimeCancelled, RuntimeExecutor
from app.runtime.models import RunRecord, RunStatus
from app.runtime.observation import observation_policy
from app.runtime.store_factory import get_run_store
from app.conversation.models import MessageCreate, MessageRole
from app.conversation.store_factory import get_conversation_store
from app.iam.models import Principal

logger = logging.getLogger(__name__)


class InProcessRuntimeWorker:
    """Development worker that exercises the platform runtime contract end-to-end."""

    def __init__(self, store: Any | None = None, executor: RuntimeExecutor | None = None) -> None:
        self._store = store or get_run_store()
        self._executor = executor or RuntimeExecutor()
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def submit(self, run: RunRecord) -> None:
        if run.status != RunStatus.RUNNING or str(run.run_id) in self._tasks:
            return
        task = asyncio.create_task(self._execute(run), name=f"agent-run-{run.run_id}")
        self._tasks[str(run.run_id)] = task
        task.add_done_callback(lambda _: self._tasks.pop(str(run.run_id), None))

    async def submit_next(self, thread_id, tenant_id: str, user_id: str) -> None:
        run = await self._store.active_for_thread(thread_id, tenant_id, user_id)
        if run is not None:
            self.submit(run)

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _execute(self, run: RunRecord) -> None:
        async def emit(event: str, data: dict) -> None:
            await self._store.append_runtime_event(
                run.run_id,
                event,
                observation_policy.sanitize_event(event, data),
                run.tenant_id,
                run.user_id,
            )

        async def is_cancelled() -> bool:
            return await self._store.is_cancelled(run.run_id, run.tenant_id, run.user_id)

        try:
            result = await self._executor.execute(run, emit, is_cancelled)
            if await is_cancelled():
                return
            await emit("runtime.completed", {"metadata": result.metadata})
            if run.conversation_id is not None:
                principal = Principal(provider="runtime", external_user_id=run.user_id, external_org_id="runtime", tenant_id=run.tenant_id, display_name="Runtime")
                await get_conversation_store().create_message(
                    run.thread_id,
                    MessageCreate(role=MessageRole.ASSISTANT, content=result.output, source_run_id=run.run_id),
                    principal,
                )
            completed = await self._store.finish(
                run.run_id,
                RunStatus.COMPLETED,
                tenant_id=run.tenant_id,
                user_id=run.user_id,
            )
            await self.submit_next(completed.thread_id, run.tenant_id, run.user_id)
        except RuntimeCancelled:
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if not await is_cancelled():
                code = getattr(exc, "code", "RUNTIME_EXECUTION_FAILED")
                logger.exception("Run execution failed run_id=%s code=%s", run.run_id, code)
                await emit("runtime.failed", {"code": code, "error_type": type(exc).__name__})
                failed = await self._store.finish(
                    run.run_id,
                    RunStatus.FAILED,
                    tenant_id=run.tenant_id,
                    user_id=run.user_id,
                )
                await self.submit_next(failed.thread_id, run.tenant_id, run.user_id)


class DisabledRuntimeWorker:
    def submit(self, run: RunRecord) -> None:
        return None

    async def submit_next(self, thread_id, tenant_id: str, user_id: str) -> None:
        return None

    async def shutdown(self) -> None:
        return None


class PollingRuntimeWorker(InProcessRuntimeWorker):
    """One-concurrency database worker used by Compose production deployments."""

    async def run_forever(self) -> None:
        settings = get_settings()
        while True:
            run = await self._store.claim_next_for_worker(settings.worker_id)
            if run is None:
                await asyncio.sleep(settings.worker_poll_interval_seconds)
                continue
            await self._execute(run)


_worker: InProcessRuntimeWorker | DisabledRuntimeWorker | None = None


def get_runtime_worker() -> InProcessRuntimeWorker | DisabledRuntimeWorker:
    global _worker
    if _worker is None:
        _worker = DisabledRuntimeWorker() if get_settings().runtime_execution_mode in {"disabled", "worker"} else InProcessRuntimeWorker()
    return _worker
