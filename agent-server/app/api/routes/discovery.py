from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.dependencies import require_platform_admin, require_platform_admin_read
from app.governance.store_factory import get_governance_store
from app.iam.models import Principal
from app.resources.discovery import get_resource_discovery_service
from app.resources.registry_factory import get_resource_registry
from app.resources.registry_models import ResourceDiscoverySnapshotRecord, ResourceDriftReport


router = APIRouter(tags=["resource-discovery"])
registry = get_resource_registry()
discovery = get_resource_discovery_service()


class DriftCheckRequest(BaseModel):
    create_draft: bool = True


@router.get(
    "/resource-versions/{resource_version_id}/discovery-snapshots",
    response_model=list[ResourceDiscoverySnapshotRecord],
)
async def list_discovery_snapshots(
    resource_version_id: UUID,
    principal: Principal = Depends(require_platform_admin_read),
) -> list[ResourceDiscoverySnapshotRecord]:
    await registry.get_version(resource_version_id, principal, published=True)
    return await discovery.list(resource_version_id, principal)


@router.post(
    "/resource-versions/{resource_version_id}/drift-check",
    response_model=ResourceDriftReport,
)
async def check_resource_drift(
    resource_version_id: UUID,
    request: DriftCheckRequest | None = None,
    principal: Principal = Depends(require_platform_admin),
) -> ResourceDriftReport:
    record = await registry.get_version(resource_version_id, principal, published=True)
    report = await discovery.check_drift(
        record, principal, create_draft=request.create_draft if request else True,
    )
    await get_governance_store().record_audit(
        principal,
        "resource.discovery.drift_check",
        record.resource_type.value,
        str(record.resource_version_id),
        {
            "provider": report.provider,
            "status": report.status.value,
            "draft_version_id": str(report.draft_version_id) if report.draft_version_id else None,
        },
    )
    return report
