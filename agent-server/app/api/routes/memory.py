from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.dependencies import ensure_resource_action, require_fresh_mutation_principal, require_fresh_principal
from app.control_plane.assembly import is_resource_assembly_v2
from app.control_plane.store_factory import get_control_plane_store
from app.core.errors import ApiError
from app.iam.models import Principal
from app.memory.models import MemoryCreate, MemoryItem
from app.memory.store import MemoryStore
from app.resources.registry_factory import get_resource_registry
from app.runtime.store_factory import get_run_store

router = APIRouter(tags=["memory"])
store = MemoryStore()


async def _memory_policy(deployment_id: UUID, principal: Principal) -> dict:
    resolved = await get_control_plane_store().resolve(deployment_id, principal)
    specification = resolved.agent_version.specification
    policy_id = specification.get("memory_policy_version_id") if is_resource_assembly_v2(specification) else None
    if not policy_id:
        raise ApiError(409, "MEMORY_DISABLED", "active deployment does not have a Memory Policy")
    await ensure_resource_action(principal, "USE", "MEMORY_POLICY", str(policy_id))
    policy = await get_resource_registry().get_version(UUID(str(policy_id)), principal, published=True)
    return policy.config


@router.post("/memory-items", response_model=MemoryItem, status_code=201)
async def create_memory(request: MemoryCreate, principal: Principal = Depends(require_fresh_mutation_principal)) -> MemoryItem:
    policy = await _memory_policy(request.deployment_id, principal)
    if request.source_run_id is not None:
        source_run = await get_run_store().get(request.source_run_id, principal)
        if source_run.deployment_id != request.deployment_id:
            raise ApiError(409, "MEMORY_SOURCE_DEPLOYMENT_MISMATCH", "source Run does not belong to deployment")
    if not policy.get("write_enabled", False) or policy.get("write_mode", "EXPLICIT") != "EXPLICIT":
        raise ApiError(403, "MEMORY_WRITE_FORBIDDEN", "Memory Policy does not allow explicit user writes")
    allowed = policy.get("allowed_categories", [])
    if allowed and request.category not in allowed:
        raise ApiError(422, "MEMORY_CATEGORY_FORBIDDEN", "memory category is not allowed by the active policy")
    max_expiry = datetime.now(timezone.utc) + timedelta(days=int(policy.get("ttl_days", 30)))
    expires_at = request.expires_at or max_expiry
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at > max_expiry + timedelta(seconds=1):
        raise ApiError(422, "MEMORY_TTL_EXCEEDED", "memory expiry exceeds the active policy TTL")
    return await store.create(
        request.model_copy(update={"expires_at": expires_at}),
        principal,
        int(policy.get("max_items", 50)),
    )


@router.get("/deployments/{deployment_id}/memory-items", response_model=list[MemoryItem])
async def list_my_memory(deployment_id: UUID, principal: Principal = Depends(require_fresh_principal)) -> list[MemoryItem]:
    policy = await _memory_policy(deployment_id, principal)
    if not policy.get("read_enabled", False):
        raise ApiError(403, "MEMORY_READ_FORBIDDEN", "Memory Policy does not allow memory reads")
    return await store.list_mine(deployment_id, principal)


@router.delete("/memory-items/{memory_id}", status_code=204)
async def delete_my_memory(memory_id: UUID, principal: Principal = Depends(require_fresh_mutation_principal)) -> None:
    await store.delete_mine(memory_id, principal)
