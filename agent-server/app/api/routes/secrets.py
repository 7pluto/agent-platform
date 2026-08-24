from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from uuid import UUID

from app.api.dependencies import require_platform_admin, require_platform_admin_read
from app.governance.store_factory import get_governance_store
from app.iam.models import Principal
from app.secrets.vault import SecretCreate, SecretRecord, SecretRotate, get_secret_vault


router = APIRouter(tags=["secret-vault"])


class SecretPublicRecord(BaseModel):
    """Safe administrator view; the internal vault URI never crosses the API."""

    secret_id: UUID
    name: str
    fingerprint: str
    status: str
    last_used_at: datetime | None = None
    rotated_at: datetime | None = None
    disabled_at: datetime | None = None
    created_by: str
    created_at: datetime


def _public(record: SecretRecord) -> SecretPublicRecord:
    prefix = "vault://"
    if not record.secret_ref.startswith(prefix):
        raise ValueError("vault returned an invalid internal secret reference")
    return SecretPublicRecord(
        secret_id=UUID(record.secret_ref.removeprefix(prefix)),
        name=record.name,
        fingerprint=record.fingerprint,
        status=record.status,
        last_used_at=record.last_used_at,
        rotated_at=record.rotated_at,
        disabled_at=record.disabled_at,
        created_by=record.created_by,
        created_at=record.created_at,
    )


@router.post("/secrets", response_model=SecretPublicRecord, status_code=201)
async def create_secret(request: SecretCreate, principal: Principal = Depends(require_platform_admin)) -> SecretPublicRecord:
    record = await get_secret_vault().create(request.name, request.value, principal)
    public = _public(record)
    await get_governance_store().record_audit(principal, "secret.create", "SECRET", str(public.secret_id), {"name": record.name, "fingerprint": record.fingerprint})
    return public


@router.get("/secrets", response_model=list[SecretPublicRecord])
async def list_secrets(principal: Principal = Depends(require_platform_admin_read)) -> list[SecretPublicRecord]:
    return [_public(record) for record in await get_secret_vault().list(principal)]


@router.post("/secrets/{secret_id}/rotate", response_model=SecretPublicRecord)
async def rotate_secret(secret_id: UUID, request: SecretRotate, principal: Principal = Depends(require_platform_admin)) -> SecretPublicRecord:
    record = await get_secret_vault().rotate(secret_id, request.value, principal)
    await get_governance_store().record_audit(principal, "secret.rotate", "SECRET", str(secret_id), {"fingerprint": record.fingerprint})
    return _public(record)


@router.post("/secrets/{secret_id}/disable", response_model=SecretPublicRecord)
async def disable_secret(secret_id: UUID, principal: Principal = Depends(require_platform_admin)) -> SecretPublicRecord:
    record = await get_secret_vault().disable(secret_id, principal)
    await get_governance_store().record_audit(principal, "secret.disable", "SECRET", str(secret_id), {"status": record.status})
    return _public(record)
