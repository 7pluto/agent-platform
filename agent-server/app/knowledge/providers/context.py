"""Build an executable Knowledge provider configuration from immutable resources.

The runtime receives only a published Knowledge version.  Connections are
resolved here so individual runtime paths never need provider-specific wiring.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.core.errors import ApiError
from app.iam.models import Principal
from app.resources.registry_factory import get_resource_registry
from app.resources.registry_models import ResourceType, ResourceVersionRecord


async def resolve_knowledge_provider_config(
    resource: ResourceVersionRecord, principal: Principal
) -> dict[str, Any]:
    if resource.resource_type != ResourceType.KNOWLEDGE:
        raise ApiError(422, "INVALID_KNOWLEDGE_RESOURCE", "resource version must be published Knowledge")
    config = dict(resource.config or {})
    connection_version_id = config.get("connection_version_id")
    if not connection_version_id:
        return config
    try:
        connection_id = UUID(str(connection_version_id))
    except (TypeError, ValueError) as exc:
        raise ApiError(422, "INVALID_KNOWLEDGE_CONNECTION", "knowledge connection version must be a UUID") from exc
    connection = await get_resource_registry().get_version(connection_id, principal, published=True)
    if connection.resource_type != ResourceType.KNOWLEDGE_CONNECTION:
        raise ApiError(422, "INVALID_KNOWLEDGE_CONNECTION", "knowledge connection must be a published Knowledge Connection")
    # Connection carries transport and secret configuration; the Knowledge
    # version remains authoritative for the selected external dataset/index.
    return {**connection.config, **config}
