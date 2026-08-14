from fastapi import APIRouter, Depends

from app.api.dependencies import require_platform_admin, require_platform_admin_read
from app.governance.store_factory import get_governance_store
from app.iam.models import Principal
from app.secrets.vault import SecretCreate, SecretRecord, get_secret_vault


router = APIRouter(tags=["secret-vault"])


@router.post("/secrets", response_model=SecretRecord, status_code=201)
async def create_secret(request: SecretCreate, principal: Principal = Depends(require_platform_admin)) -> SecretRecord:
    record = await get_secret_vault().create(request.name, request.value, principal)
    await get_governance_store().record_audit(principal, "secret.create", "SECRET", record.secret_ref, {"name": record.name, "fingerprint": record.fingerprint})
    return record


@router.get("/secrets", response_model=list[SecretRecord])
async def list_secrets(principal: Principal = Depends(require_platform_admin_read)) -> list[SecretRecord]:
    return await get_secret_vault().list(principal)
