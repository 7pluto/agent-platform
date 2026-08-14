from __future__ import annotations

from typing import Any
from uuid import UUID

from app.core.errors import ApiError
from app.control_plane.assembly import agent_resource_ids, is_resource_assembly_v2, reject_legacy_text_resources


def validate_agent_specification(specification: dict[str, Any]) -> None:
    """Validate platform-owned, harness-neutral Agent version declarations."""
    builder = specification.get("builder")
    if builder is not None:
        if not isinstance(builder, dict) or builder.get("id") not in {"react", "router", "custom"}:
            raise ApiError(422, "INVALID_BUILDER", "builder.id must be react, router, or custom")
        if not isinstance(builder.get("version"), str) or not builder["version"].strip():
            raise ApiError(422, "INVALID_BUILDER", "builder.version is required")
    model_version_reference(specification)
    if is_resource_assembly_v2(specification):
        reject_legacy_text_resources(specification)
        agent_resource_ids(specification)
    for key in ("model_ref", "prompt_ref"):
        reference = specification.get(key)
        if reference is not None and (not isinstance(reference, str) or not reference.strip()):
            raise ApiError(422, "INVALID_RESOURCE_REFERENCE", f"{key} must be a non-empty opaque version reference")

def model_version_reference(specification: dict[str, Any]) -> UUID | None:
    """Read the Stage 4.1 immutable model version reference, if present."""
    reference = specification.get("model_version_id")
    if reference is None:
        return None
    try:
        return UUID(str(reference))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ApiError(422, "INVALID_MODEL_REFERENCE", "model_version_id must be a UUID") from exc
