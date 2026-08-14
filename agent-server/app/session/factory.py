from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.session.redis_store import RedisSessionStore
from app.session.store import SessionStore


@lru_cache
def get_session_store() -> SessionStore | RedisSessionStore:
    if get_settings().session_storage_mode == "redis":
        return RedisSessionStore(get_settings())
    return SessionStore(get_settings())


async def close_session_store() -> None:
    await get_session_store().close()