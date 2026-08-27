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
    # Immutable authorization decision captured at submission time.  A false
    # value is retained only for historical manifests created before strict
    # dependency authorization became the Run-start rule.
    use_allowed: bool = True


class BuilderMetadata(BaseModel):
    id: str = "react"
    version: str = "1"


class HarnessMetadata(BaseModel):
    type: str = "mock"
    version: str = "0.1.0"


class ExecutionManifest(BaseModel):
    """Internal immutable execution snapshot for one Run.

    This model is persisted and consumed by the Worker.  It must never be used
    directly as an HTTP response model because historical manifests can contain
    server-only binding material such as secret references or provider config.
    """

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
    # Compatibility-only internal field. New HTTP responses use
    # PublicExecutionManifest and never expose it.
    secret_refs: dict[str, str] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    manifest_hash: str = ""


_PUBLIC_RESOURCE_VERSION_KEYS = frozenset({
    "agent_definition_id",
    "agent_version_id",
    "agent_version_content_hash",
    "deployment_revision_id",
    "model_version_id",
    "model_version_content_hash",
})


class PublicExecutionManifest(BaseModel):
    """Secret-free HTTP representation of an ExecutionManifest."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str
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
    generated_at: datetime
    manifest_hash: str

    @classmethod
    def from_internal(cls, manifest: ExecutionManifest) -> "PublicExecutionManifest":
        return cls(
            schema_version=manifest.schema_version,
            tenant_id=manifest.tenant_id,
            run_id=manifest.run_id,
            thread_id=manifest.thread_id,
            deployment_id=manifest.deployment_id,
            deployment_revision_id=manifest.deployment_revision_id,
            runtime=manifest.runtime,
            builder=manifest.builder,
            harness=manifest.harness,
            resource_versions={
                key: value
                for key, value in manifest.resource_versions.items()
                if key in _PUBLIC_RESOURCE_VERSION_KEYS
            },
            resources=list(manifest.resources),
            policy_versions=dict(manifest.policy_versions),
            generated_at=manifest.generated_at,
            manifest_hash=manifest.manifest_hash,
        )


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


class PublicRunRecord(BaseModel):
    """HTTP-safe Run record. The Worker-only manifest never crosses the API."""

    run_id: UUID
    tenant_id: str
    user_id: str
    deployment_id: UUID
    thread_id: UUID
    conversation_id: UUID | None = None
    message: str
    status: RunStatus
    created_at: datetime
    execution_manifest: PublicExecutionManifest | None = None

    @classmethod
    def from_internal(cls, record: RunRecord) -> "PublicRunRecord":
        return cls(
            run_id=record.run_id,
            tenant_id=record.tenant_id,
            user_id=record.user_id,
            deployment_id=record.deployment_id,
            thread_id=record.thread_id,
            conversation_id=record.conversation_id,
            message=record.message,
            status=record.status,
            created_at=record.created_at,
            execution_manifest=(
                PublicExecutionManifest.from_internal(record.execution_manifest)
                if record.execution_manifest is not None
                else None
            ),
        )


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
    """Internal replay-safe read model."""

    run: RunRecord
    manifest: ExecutionManifest
    events: list[RunEvent]


class PublicRunDetail(BaseModel):
    """HTTP-safe Run detail with a redacted immutable manifest."""

    run: PublicRunRecord
    manifest: PublicExecutionManifest
    events: list[RunEvent]

    @classmethod
    def from_internal(cls, record: RunRecord, events: list[RunEvent]) -> "PublicRunDetail":
        if record.execution_manifest is None:
            raise ValueError("run has no execution manifest")
        return cls(
            run=PublicRunRecord.from_internal(record),
            manifest=PublicExecutionManifest.from_internal(record.execution_manifest),
            events=events,
        )
