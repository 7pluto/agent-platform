import asyncio
from uuid import UUID
from sqlalchemy import text
from app.db.session import get_session_factory

RUN = UUID("12e0f7d4-6e49-416e-abc6-261914c47c55")

async def main():
    async with get_session_factory()() as session:
        for sql, params in [
            ("select run_id,status,tenant_id,user_id,deployment_id,created_at from platform_run where run_id=:run", {"run": RUN}),
            ("select sequence,event,data from platform_run_event where run_id=:run order by sequence", {"run": RUN}),
            ("select run_id,claimed_by,attempt,lease_expires_at,available_at from platform_run_scheduler_queue where run_id=:run", {"run": RUN}),
            ("select tenant_id,thread_id,active_run_id,lease_until from platform_thread_lease where active_run_id=:run", {"run": RUN}),
        ]:
            result = await session.execute(text(sql), params)
            print([dict(row) for row in result.mappings().all()])

asyncio.run(main())
