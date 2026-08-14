from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class MemoryCreate(BaseModel):
    deployment_id: UUID
    category: str = Field(default="preference", min_length=1, max_length=64)
    content: str = Field(min_length=1, max_length=4_000)
    expires_at: datetime | None = None
    source_run_id: UUID | None = None


class MemoryItem(MemoryCreate):
    memory_id: UUID
    tenant_id: str
    user_id: str
    source_run_id: UUID | None = None
    created_at: datetime
