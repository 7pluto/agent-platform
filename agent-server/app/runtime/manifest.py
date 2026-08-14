from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from uuid import UUID
from typing import Any

from app.runtime.models import (
    BuilderMetadata,
    ExecutionManifest,
    HarnessMetadata,
    RunRecord,
    RuntimeMetadata,
    ManifestResource,
)


def build_execution_manifest(
    record: RunRecord,
    *,
    generated_at: datetime | None = None,
    deployment_revision_id: UUID | None = None,
    resource_versions: dict[str, str] | None = None,
    policy_versions: dict[str, str] | None = None,
    secret_refs: dict[str, str] | None = None,
    resources: list[dict[str, Any]] | None = None,
    harness_type: str = "mock",
    harness_version: str = "0.1.0",
) -> ExecutionManifest:
    """Build a deterministic, secret-free manifest bound to a Run."""

    manifest = ExecutionManifest(
        tenant_id=record.tenant_id,
        run_id=record.run_id,
        thread_id=record.thread_id,
        deployment_id=record.deployment_id,
        deployment_revision_id=deployment_revision_id,
        runtime=RuntimeMetadata(
            version=os.getenv("AGENT_RUNTIME_VERSION", "0.1.0"),
            git_commit=os.getenv("AGENT_RUNTIME_GIT_COMMIT", "unknown"),
            image_digest=os.getenv("AGENT_RUNTIME_IMAGE_DIGEST", "unknown"),
        ),
        builder=BuilderMetadata(),
        harness=HarnessMetadata(type=harness_type, version=harness_version),
        resource_versions=dict(resource_versions or {}),
        schema_version="3" if any("binding_origin" in value for value in resources or []) else "2",
        resources=[ManifestResource.model_validate(value) for value in resources or []],
        policy_versions=dict(policy_versions or {}),
        secret_refs=dict(secret_refs or {}),
        generated_at=generated_at or datetime.now(timezone.utc),
    )
    digest = hashlib.sha256(_canonical_json(manifest.model_dump(mode="json", exclude={"manifest_hash"}))).hexdigest()
    return manifest.model_copy(update={"manifest_hash": digest})


def _canonical_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
