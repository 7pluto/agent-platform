from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.dependencies import require_platform_admin, require_platform_admin_read
from app.core.errors import ApiError
from app.governance.store_factory import get_governance_store
from app.iam.models import Principal
from app.resources.models import ModelConnectionTestResult, ModelDefinitionCreate, ModelDefinitionRecord, ModelVersionCreate, ModelVersionRecord
from app.resources.openai_compatible import OpenAICompatibleModel
from app.resources.store_factory import get_resource_store
from app.secrets.vault import get_secret_vault

router = APIRouter(tags=["resources"])
store = get_resource_store()


class ModelWithSecretCreate(BaseModel):
    slug: str = Field(pattern=r"^[a-z][a-z0-9-]{2,63}$")
    display_name: str = Field(min_length=1, max_length=128)
    base_url: str
    model: str = Field(min_length=1, max_length=256)
    api_key: str = Field(min_length=1, max_length=32_768)
    model_mode: str = Field(default="CHAT", pattern=r"^(CHAT|EMBEDDING)$")


@router.post("/models/with-secret", response_model=ModelVersionRecord, status_code=201)
async def create_model_with_secret(request: ModelWithSecretCreate, principal: Principal = Depends(require_platform_admin)) -> ModelVersionRecord:
    if request.model_mode == "CHAT":
        candidate = OpenAICompatibleModel(request.base_url.rstrip("/"), request.model, request.api_key)
        await candidate.test_connection()
    else:
        from app.resources.openai_compatible import OpenAICompatibleEmbedder
        candidate = OpenAICompatibleEmbedder(request.base_url.rstrip("/"), request.model, request.api_key)
        await candidate.embed(["embedding connection test"])
    secret = await get_secret_vault().create(f"Model: {request.display_name}", request.api_key, principal)
    config = {"base_url": request.base_url.rstrip("/"), "model": request.model, "model_mode": request.model_mode, "secret_ref": secret.secret_ref}
    definition = await store.create_model(ModelDefinitionCreate(slug=request.slug, display_name=request.display_name, config=config), principal)
    version = await store.create_model_version(definition.model_id, ModelVersionCreate(config=config), principal)
    await store.record_connection_test(version.model_version_id, principal, True, "connection successful")
    published = await store.publish_model_version(version.model_version_id, principal)
    await get_governance_store().record_audit(principal, "model.publish_with_vault_secret", "MODEL_VERSION", str(published.model_version_id), {"model_id": str(published.model_id), "secret_ref": secret.secret_ref, "fingerprint": secret.fingerprint})
    return published


@router.post("/models", response_model=ModelDefinitionRecord, status_code=201)
async def create_model(request: ModelDefinitionCreate, principal: Principal = Depends(require_platform_admin)) -> ModelDefinitionRecord:
    result = await store.create_model(request, principal)
    await get_governance_store().record_audit(principal, "model.create", "MODEL", str(result.model_id), {"provider": result.provider})
    return result


@router.get("/models", response_model=list[ModelDefinitionRecord])
async def list_models(principal: Principal = Depends(require_platform_admin_read)) -> list[ModelDefinitionRecord]:
    return await store.list_models(principal)


@router.post("/models/{model_id}/versions", response_model=ModelVersionRecord, status_code=201)
async def create_model_version(model_id: UUID, request: ModelVersionCreate, principal: Principal = Depends(require_platform_admin)) -> ModelVersionRecord:
    return await store.create_model_version(model_id, request, principal)


@router.get("/models/{model_id}/versions", response_model=list[ModelVersionRecord])
async def list_model_versions(model_id: UUID, principal: Principal = Depends(require_platform_admin_read)) -> list[ModelVersionRecord]:
    return await store.list_model_versions(model_id, principal)


@router.post("/model-versions/{model_version_id}/test", response_model=ModelConnectionTestResult)
async def test_model_version(model_version_id: UUID, principal: Principal = Depends(require_platform_admin)) -> ModelConnectionTestResult:
    version = await store.get_model_version(model_version_id, principal)
    try:
        await (await OpenAICompatibleModel.from_runtime_config(version.config, principal.tenant_id, principal.external_user_id)).test_connection()
    except ApiError as exc:
        await store.record_connection_test(model_version_id, principal, False, exc.code)
        raise
    result = await store.record_connection_test(model_version_id, principal, True, "connection successful")
    await get_governance_store().record_audit(principal, "model.test", "MODEL_VERSION", str(model_version_id), {"available": result.available})
    return result


@router.post("/model-versions/{model_version_id}/publish", response_model=ModelVersionRecord)
async def publish_model_version(model_version_id: UUID, principal: Principal = Depends(require_platform_admin)) -> ModelVersionRecord:
    result = await store.publish_model_version(model_version_id, principal)
    await get_governance_store().record_audit(principal, "model.publish", "MODEL_VERSION", str(model_version_id), {})
    return result
