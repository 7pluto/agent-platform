from functools import lru_cache

from app.config import get_settings
from app.resources.postgres_store import PostgresResourceStore
from app.resources.store import ResourceStore


@lru_cache
def get_resource_store() -> ResourceStore | PostgresResourceStore:
    return PostgresResourceStore() if get_settings().storage_mode == "postgres" else ResourceStore()