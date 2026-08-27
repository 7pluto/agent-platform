from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.dependencies import ensure_resource_action, require_resource_developer_read
from app.core.errors import ApiError
from app.iam.models import Principal
from app.knowledge.jobs import ingest_jobs
from app.knowledge.models import IngestJobRecord
from app.resources.registry_factory import get_resource_registry
from app.resources.registry_models import ResourceType

router = APIRouter(prefix="/developer/external/knowledge", tags=["developer-knowledge-ops"])


@router.get("/{resource_version_id}/jobs", response_model=list[IngestJobRecord])
async def list_developer_knowledge_jobs(
    resource_version_id: UUID,
    principal: Principal = Depends(require_resource_developer_read),
) -> list[IngestJobRecord]:
    record = await get_resource_registry().get_version(resource_version_id, principal, published=True)
    if record.resource_type != ResourceType.KNOWLEDGE:
        raise ApiError(422, "RESOURCE_TYPE_MISMATCH", "resource version is not Knowledge")
    await ensure_resource_action(principal, "USE", ResourceType.KNOWLEDGE.value, str(resource_version_id))
    return await ingest_jobs.list_for_knowledge(principal, resource_version_id)
