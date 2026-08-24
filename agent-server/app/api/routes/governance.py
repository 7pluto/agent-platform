from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.dependencies import require_platform_admin, require_platform_admin_read
from app.governance.models import AuditEventRecord, ResourceGrantCreate, ResourceGrantRecord
from app.governance.store_factory import get_governance_store
from app.iam.models import Principal

router = APIRouter(tags=["governance"])
store = get_governance_store()


@router.post("/resource-grants", response_model=ResourceGrantRecord, status_code=201)
async def create_resource_grant(
    request: ResourceGrantCreate,
    principal: Principal = Depends(require_platform_admin),
) -> ResourceGrantRecord:
    record = await store.create_grant(request, principal)
    await store.record_audit(
        principal,
        "resource_grant.create",
        "RESOURCE_GRANT",
        str(record.grant_id),
        {
            "subject_type": record.subject_type.value,
            "subject_id": record.subject_id,
            "resource_type": record.resource_type,
            "resource_id": record.resource_id,
            "actions": sorted(record.actions),
            "effect": record.effect.value,
        },
    )
    return record


@router.get("/resource-grants", response_model=list[ResourceGrantRecord])
async def list_resource_grants(
    resource_type: str | None = Query(default=None),
    resource_id: str | None = Query(default=None),
    principal: Principal = Depends(require_platform_admin_read),
) -> list[ResourceGrantRecord]:
    return await store.list_grants(principal, resource_type, resource_id)


@router.delete("/resource-grants/{grant_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_resource_grant(
    grant_id: UUID,
    principal: Principal = Depends(require_platform_admin),
) -> Response:
    record = await store.delete_grant(grant_id, principal)
    if record is None:
        raise HTTPException(status_code=404, detail={"code": "RESOURCE_GRANT_NOT_FOUND", "message": "resource grant not found"})
    await store.record_audit(
        principal,
        "resource_grant.delete",
        "RESOURCE_GRANT",
        str(grant_id),
        {
            "subject_type": record.subject_type.value,
            "subject_id": record.subject_id,
            "resource_type": record.resource_type,
            "resource_id": record.resource_id,
            "actions": sorted(record.actions),
            "effect": record.effect.value,
        },
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/audit-events", response_model=list[AuditEventRecord])
async def list_audit_events(
    limit: int = Query(default=100, ge=1, le=500),
    principal: Principal = Depends(require_platform_admin_read),
) -> list[AuditEventRecord]:
    return await store.list_audit(principal, limit)
