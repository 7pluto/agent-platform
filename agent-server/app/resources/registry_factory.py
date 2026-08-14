from functools import lru_cache

from app.config import get_settings
from app.resources.registry_postgres_store import PostgresResourceRegistryStore
from app.resources.registry_store import ResourceRegistryStore


@lru_cache
def get_resource_registry():
    return PostgresResourceRegistryStore() if get_settings().storage_mode == "postgres" else ResourceRegistryStore()
