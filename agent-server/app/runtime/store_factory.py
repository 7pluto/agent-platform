from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.runtime.postgres_store import PostgresRunStore
from app.runtime.store import RunStore


@lru_cache
def get_run_store() -> RunStore | PostgresRunStore:
    if get_settings().storage_mode == "postgres":
        return PostgresRunStore()
    return RunStore()


async def close_run_store() -> None:
    store = get_run_store()
    if isinstance(store, PostgresRunStore):
        await store.close()