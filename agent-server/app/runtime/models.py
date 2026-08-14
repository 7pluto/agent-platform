from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class RunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"


class RuntimeMetadata(BaseModel):
    version: str = "0.1.0"
    git_commit: str = "unknown"
    image_digest: str = "unknown"


class ManifestResource(BaseModel):
    type: str
    resource_id: str
    version_id: str
    content_hash: str
    binding_origin: str = "DIRECT"
    dependency_path: list[str] = Field(default_factory=list)
    # Kept in the canonical manifest so retries and historical Run replay use
    # the same authorization decision as the original submission.
    use_allowed: bool = True


class BuilderMetadata(BaseModel):
    id: str = "react"
    version: str = "1"


class HarnessMetadata(BaseModel):
    type: str = "mock"
    version: str = "0.1.0"


class ExecutionManifest(BaseModel):
    """Immutable, secret-free input snapshot for one Run execution."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = "2"
    tenant_id: str
    run_id: UUID
    thread_id: UUID
    deployment_id: UUID
    deployment_revision_id: UUID | None = None
    runtime: RuntimeMetadata
    builder: BuilderMetadata
    harness: HarnessMetadata
    resource_versions: dict[str, str] = Field(default_factory=dict)
    resources: list[ManifestResource] = Field(default_factory=list)
    policy_versions: dict[str, str] = Field(default_factory=dict)
    secret_refs: dict[str, str] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    manifest_hash: str = ""


class RunCreateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    deployment_id: UUID
    message: str = Field(min_length=1, max_length=100_000)
    thread_id: UUID | None = None
    conversation_id: UUID | None = None
    # Compatibility-only fields. Routes reject mismatches with the trusted Principal.
    user_id: str | None = None
    tenant_id: str | None = None


class RunRecord(BaseModel):
    run_id: UUID = Field(default_factory=uuid4)
    tenant_id: str
    user_id: str
    deployment_id: UUID
    thread_id: UUID
    conversation_id: UUID | None = None
    message: str
    status: RunStatus = RunStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    execution_manifest: ExecutionManifest | None = None


class RunEvent(BaseModel):
    sequence: int
    event_id: UUID = Field(default_factory=uuid4)
    event: str
    run_id: UUID
    thread_id: UUID
    trace_id: str
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    data: dict[str, Any] = Field(default_factory=dict)


class RunDetail(BaseModel):
    """A replay-safe read model for the Run Detail screen."""

    run: RunRecord
    manifest: ExecutionManifest
    events: list[RunEvent]
