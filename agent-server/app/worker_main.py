from __future__ import annotations

import asyncio
import logging

from app.config import get_settings
from app.runtime.postgres_store import PostgresRunStore
from app.runtime.worker import PollingRuntimeWorker
from app.knowledge.jobs import ingest_jobs
from app.knowledge.ingest import knowledge_ingestor

logger = logging.getLogger(__name__)


async def main() -> None:
    if get_settings().runtime_execution_mode != "worker":
        raise RuntimeError("AGENT_RUNTIME_EXECUTION_MODE must be worker")
    worker = PollingRuntimeWorker(store=PostgresRunStore())
    settings = get_settings()
    while True:
        job = await ingest_jobs.claim(settings.worker_id)
        if job:
            try:
                await knowledge_ingestor.build(job.tenant_id, job.user_id, job.knowledge_resource_version_id)
            except Exception as exc:
                error_code = getattr(exc, "code", "INGEST_FAILED")
                logger.exception("Knowledge ingest failed job_id=%s code=%s", job.job_id, error_code)
                await ingest_jobs.finish(job.job_id, error_code)
            else:
                await ingest_jobs.finish(job.job_id)
            continue
        run = await worker._store.claim_next_for_worker(settings.worker_id)
        if run:
            await worker._execute(run)
            continue
        await asyncio.sleep(settings.worker_poll_interval_seconds)


if __name__ == "__main__":
    asyncio.run(main())
