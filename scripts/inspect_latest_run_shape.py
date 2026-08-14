import asyncio
from sqlalchemy import text
from app.db.session import get_session_factory

async def main():
    async with get_session_factory()() as session:
        run = (await session.execute(text("select run_id,status from platform_run order by created_at desc limit 1"))).mappings().first()
        events = (await session.execute(text("select sequence,event,data from platform_run_event where run_id=:run order by sequence"), {"run": run["run_id"]})).mappings().all()
        print({"run_id": str(run["run_id"]), "status": run["status"], "events": [item["event"] for item in events], "output_shapes": [{"sequence": item["sequence"], "keys": sorted(item["data"].keys()), "nested_keys": sorted(item["data"].get("data", {}).keys()) if isinstance(item["data"].get("data"), dict) else []} for item in events if item["event"] == "runtime.output"], "failures": [{"sequence": item["sequence"], "data": {key: item["data"].get(key) for key in ("code", "error_type", "message") if key in item["data"]}} for item in events if item["event"] == "runtime.failed"]})

asyncio.run(main())
