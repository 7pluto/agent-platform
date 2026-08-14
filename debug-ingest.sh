#!/usr/bin/env bash
set -euo pipefail
cd /home/ubuntu/agent-platform
sudo docker exec -i agent-platform-agent-worker-1 python - <<'PY'
import asyncio, traceback
from uuid import UUID
from app.knowledge.ingest import knowledge_ingestor

async def main():
    try:
        value = await knowledge_ingestor.build("tenant-demo", "user-demo", UUID("5410a2f7-0d93-4170-8857-1d1ff771c6e5"))
        print(value)
    except Exception:
        traceback.print_exc()
        raise

asyncio.run(main())
PY
