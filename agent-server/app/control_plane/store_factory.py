from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.control_plane.postgres_store import PostgresControlPlaneStore
from app.control_plane.store import ControlPlaneStore


@lru_cache
def get_control_plane_store() -> ControlPlaneStore | PostgresControlPlaneStore:
    if get_settings().storage_mode == "postgres":
        return PostgresControlPlaneStore()
    return ControlPlaneStore()