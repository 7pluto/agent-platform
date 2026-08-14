#!/usr/bin/env bash
set -euo pipefail
sudo docker exec -i agent-platform-agent-worker-1 python - <<'PY'
import asyncio, traceback
from uuid import UUID
from sqlalchemy import select
from app.db.models import RunRow
from app.db.rls import set_local_tenant_context
from app.db.session import get_session_factory
from app.runtime.adapter import RuntimeExecutor
from app.runtime.models import ExecutionManifest, RunRecord

async def main():
  async with get_session_factory()() as session:
    async with session.begin():
      await set_local_tenant_context(session,"tenant-demo","user-demo")
      row=await session.get(RunRow,UUID("127e5b24-a9c0-42e5-9d39-2a8525a27500"))
      run=RunRecord(run_id=row.run_id,tenant_id=row.tenant_id,user_id=row.user_id,deployment_id=row.deployment_id,thread_id=row.thread_id,conversation_id=row.conversation_id,message=row.message,status=row.status,created_at=row.created_at,execution_manifest=ExecutionManifest.model_validate(row.execution_manifest))
  async def emit(event,data): print(event, {k:v for k,v in data.items() if k not in {"output","resources"}})
  async def cancelled(): return False
  try: print(await RuntimeExecutor().execute(run,emit,cancelled))
  except Exception:
    traceback.print_exc()
    raise
asyncio.run(main())
PY
