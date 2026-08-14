from fastapi import APIRouter, Depends
from uuid import UUID

from app.api.dependencies import require_platform_admin, require_platform_admin_read
from app.governance.store_factory import get_governance_store
from app.iam.models import Principal
from app.secrets.vault import SecretCreate, SecretRecord, SecretRotate, get_secret_vault


router = APIRouter(tags=["secret-vault"])


@router.post("/secrets", response_model=SecretRecord, status_code=201)
async def create_secret(request: SecretCreate, principal: Principal = Depends(require_platform_admin)) -> SecretRecord:
    record = await get_secret_vault().create(request.name, request.value, principal)
    await get_governance_store().record_audit(principal, "secret.create", "SECRET", record.secret_ref, {"name": record.name, "fingerprint": record.fingerprint})
    return record


@router.get("/secrets", response_model=list[SecretRecord])
async def list_secrets(principal: Principal = Depends(require_platform_admin_read)) -> list[SecretRecord]:
    return await get_secret_vault().list(principal)


@router.post("/secrets/{secret_id}/rotate", response_model=SecretRecord)
async def rotate_secret(secret_id: UUID, request: SecretRotate, principal: Principal = Depends(require_platform_admin)) -> SecretRecord:
    record = await get_secret_vault().rotate(secret_id, request.value, principal)
    await get_governance_store().record_audit(principal, "secret.rotate", "SECRET", record.secret_ref, {"fingerprint": record.fingerprint})
    return record


@router.post("/secrets/{secret_id}/disable", response_model=SecretRecord)
async def disable_secret(secret_id: UUID, principal: Principal = Depends(require_platform_admin)) -> SecretRecord:
    record = await get_secret_vault().disable(secret_id, principal)
    await get_governance_store().record_audit(principal, "secret.disable", "SECRET", record.secret_ref, {"status": record.status})
    return record
