from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ResourceType(StrEnum):
    MODEL = "MODEL"
    PROMPT = "PROMPT"
    SKILL = "SKILL"
    TOOL = "TOOL"
    MCP_SERVER = "MCP_SERVER"
    MCP_CONNECTION = "MCP_CONNECTION"
    KNOWLEDGE_CONNECTION = "KNOWLEDGE_CONNECTION"
    KNOWLEDGE = "KNOWLEDGE"
    MEMORY_POLICY = "MEMORY_POLICY"


class ResourceVersionStatus(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    DEPRECATED = "DEPRECATED"


class ResourceValidationType(StrEnum):
    PROBE = "PROBE"
    DISCOVER = "DISCOVER"
    TEST = "TEST"
    VALIDATE = "VALIDATE"


class ResourceValidationStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class ResourceDefinitionCreate(BaseModel):
    resource_type: ResourceType
    slug: str = Field(pattern=r"^[a-z][a-z0-9-]{2,63}$")
    display_name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=4_000)
    draft_config: dict[str, Any] = Field(default_factory=dict)


class ResourceDefinitionRecord(ResourceDefinitionCreate):
    resource_id: UUID = Field(default_factory=uuid4)
    tenant_id: str
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ResourceVersionCreate(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)


class ResourceVersionRecord(BaseModel):
    resource_version_id: UUID = Field(default_factory=uuid4)
    resource_id: UUID
    tenant_id: str
    resource_type: ResourceType
    version_number: int
    status: ResourceVersionStatus = ResourceVersionStatus.DRAFT
    config: dict[str, Any]
    content_hash: str
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    published_at: datetime | None = None


class ResourceValidationRunRecord(BaseModel):
    validation_run_id: UUID = Field(default_factory=uuid4)
    tenant_id: str
    resource_version_id: UUID
    validation_type: ResourceValidationType
    status: ResourceValidationStatus
    result: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int | None = Field(default=None, ge=0)
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExternalBindingStatus(StrEnum):
    MANAGED = "MANAGED"
    CHANGED = "CHANGED"
    MISSING = "MISSING"


class ResourceExternalBindingRecord(BaseModel):
    binding_id: UUID = Field(default_factory=uuid4)
    tenant_id: str
    provider: str
    connection_resource_id: UUID
    external_type: str
    external_id: str
    resource_id: UUID
    status: ExternalBindingStatus = ExternalBindingStatus.MANAGED
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DiscoveryDriftStatus(StrEnum):
    NO_CHANGE = "NO_CHANGE"
    CHANGED = "CHANGED"
    MISSING = "MISSING"
    UNAVAILABLE = "UNAVAILABLE"


class ResourceDiscoverySnapshotRecord(BaseModel):
    snapshot_id: UUID = Field(default_factory=uuid4)
    tenant_id: str
    resource_version_id: UUID
    provider: str
    external_type: str
    external_id: str
    schema_hash: str
    snapshot: dict[str, Any] = Field(default_factory=dict)
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ResourceDriftReport(BaseModel):
    resource_version_id: UUID
    provider: str
    status: DiscoveryDriftStatus
    published_schema_hash: str
    current_schema_hash: str | None = None
    message: str | None = None
    current_snapshot: dict[str, Any] | None = None
    draft_version_id: UUID | None = None
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
