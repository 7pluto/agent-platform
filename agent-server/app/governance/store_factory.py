from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.governance.postgres_store import PostgresGovernanceStore
from app.governance.store import GovernanceStore


@lru_cache
def get_governance_store() -> GovernanceStore | PostgresGovernanceStore:
    if get_settings().storage_mode == "postgres":
        return PostgresGovernanceStore()
    return GovernanceStore()