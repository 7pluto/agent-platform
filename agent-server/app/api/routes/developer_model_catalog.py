from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.dependencies import ensure_resource_action, require_resource_developer_read
from app.core.errors import ApiError
from app.iam.models import Principal
from app.resources.models import ModelAvailability, ResourceVersionStatus
from app.resources.store_factory import get_resource_store

router = APIRouter(prefix="/developer/external/models", tags=["developer-model-catalog"])


class DeveloperTypedModelOption(BaseModel):
    model_id: UUID
    model_version_id: UUID
    display_name: str
    version_number: int
    provider: str
    model_name: str
    model_mode: Literal["CHAT", "EMBEDDING"]


async def _list_mode(mode: Literal["CHAT", "EMBEDDING"], principal: Principal) -> list[DeveloperTypedModelOption]:
    store = get_resource_store()
    result: list[DeveloperTypedModelOption] = []
    for model in await store.list_models(principal):
        for version in await store.list_model_versions(model.model_id, principal):
            if version.status != ResourceVersionStatus.PUBLISHED or version.availability != ModelAvailability.AVAILABLE:
                continue
            model_mode = str(version.config.get("model_mode") or "CHAT").upper()
            if model_mode != mode:
                continue
            try:
                await ensure_resource_action(principal, "USE", "MODEL", str(version.model_version_id))
            except ApiError as exc:
                if exc.code == "RESOURCE_FORBIDDEN":
                    continue
                raise
            result.append(DeveloperTypedModelOption(
                model_id=model.model_id,
                model_version_id=version.model_version_id,
                display_name=model.display_name,
                version_number=version.version_number,
                provider=version.provider,
                model_name=str(version.config.get("model") or model.display_name),
                model_mode=mode,
            ))
    return sorted(result, key=lambda item: (item.display_name.lower(), -item.version_number))


@router.get("/chat", response_model=list[DeveloperTypedModelOption])
async def list_chat_models(principal: Principal = Depends(require_resource_developer_read)) -> list[DeveloperTypedModelOption]:
    return await _list_mode("CHAT", principal)


@router.get("/embedding", response_model=list[DeveloperTypedModelOption])
async def list_embedding_models(principal: Principal = Depends(require_resource_developer_read)) -> list[DeveloperTypedModelOption]:
    return await _list_mode("EMBEDDING", principal)
