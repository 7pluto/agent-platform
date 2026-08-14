from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ResourceVersionStatus(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"


class ModelAvailability(StrEnum):
    UNKNOWN = "UNKNOWN"
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class ModelDefinitionCreate(BaseModel):
    slug: str = Field(pattern=r"^[a-z][a-z0-9-]{2,63}$")
    display_name: str = Field(min_length=1, max_length=128)
    provider: str = Field(default="openai-compatible", pattern=r"^openai-compatible$")
    config: dict[str, Any] = Field(default_factory=dict)


class ModelDefinitionRecord(ModelDefinitionCreate):
    model_id: UUID = Field(default_factory=uuid4)
    tenant_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ModelVersionCreate(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)


class ModelVersionRecord(BaseModel):
    model_version_id: UUID = Field(default_factory=uuid4)
    model_id: UUID
    tenant_id: str
    version_number: int
    status: ResourceVersionStatus = ResourceVersionStatus.DRAFT
    provider: str
    config: dict[str, Any]
    content_hash: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    published_at: datetime | None = None
    availability: ModelAvailability = ModelAvailability.UNKNOWN
    last_tested_at: datetime | None = None
    last_test_error: str | None = None


class ModelConnectionTestResult(BaseModel):
    available: bool
    model_version_id: UUID
    tested_at: datetime
    message: str