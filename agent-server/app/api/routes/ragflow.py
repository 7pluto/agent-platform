from __future__ import annotations

from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.dependencies import require_platform_admin
from app.core.errors import ApiError
from app.iam.models import Principal
from app.knowledge.providers.ragflow import RagflowKnowledgeProvider
from app.resources.registry_factory import get_resource_registry
from app.resources.registry_models import ResourceDefinitionCreate, ResourceType, ResourceVersionCreate, ResourceVersionRecord
from app.resources.registry_store import ResourceRegistryStore
from app.resources.discovery import get_resource_discovery_service
from app.secrets.vault import get_secret_vault

router = APIRouter(tags=["ragflow"])
discovery_snapshots = get_resource_discovery_service()

class RagflowConnectionCreate(BaseModel):
    slug: str = Field(pattern=r"^[a-z][a-z0-9-]{2,63}$")
    display_name: str
    endpoint: str
    api_key: str
    timeout_seconds: float = Field(default=20, ge=0.1, le=60)

class RagflowDatasetRegister(BaseModel):
    connection_version_id: UUID
    dataset_id: str
    slug: str = Field(pattern=r"^[a-z][a-z0-9-]{2,63}$")
    display_name: str
    description: str | None = None

@router.post("/ragflow-connections", response_model=ResourceVersionRecord, status_code=201)
async def create_ragflow_connection(request: RagflowConnectionCreate, principal: Principal = Depends(require_platform_admin)) -> ResourceVersionRecord:
    host = urlsplit(request.endpoint).hostname
    if not host:
        raise ApiError(422, "INVALID_KNOWLEDGE_CONNECTION", "endpoint must contain a hostname")
    secret = await get_secret_vault().create(f"RAGFlow: {request.display_name}", request.api_key, principal)
    config = {"provider": "RAGFLOW", "endpoint": request.endpoint.rstrip("/"), "secret_ref": secret.secret_ref, "auth_header": "Authorization", "auth_scheme": "Bearer", "timeout_seconds": request.timeout_seconds, "egress_allowlist": [host]}
    ResourceRegistryStore._validate(ResourceType.KNOWLEDGE_CONNECTION, config)
    registry = get_resource_registry()
    definition = await registry.create_definition(ResourceDefinitionCreate(resource_type=ResourceType.KNOWLEDGE_CONNECTION, slug=request.slug, display_name=request.display_name, draft_config=config), principal)
    version = await registry.create_version(definition.resource_id, ResourceVersionCreate(config=config), principal)
    return await registry.publish_version(version.resource_version_id, principal)

@router.post("/ragflow-connections/{resource_version_id}/discover")
async def discover_ragflow_datasets(resource_version_id: UUID, principal: Principal = Depends(require_platform_admin)) -> list[dict]:
    connection = await get_resource_registry().get_version(resource_version_id, principal, published=True)
    if connection.resource_type != ResourceType.KNOWLEDGE_CONNECTION:
        raise ApiError(422, "RESOURCE_TYPE_MISMATCH", "resource version is not a knowledge connection")
    return await RagflowKnowledgeProvider(principal).discover_datasets(connection.config)

@router.post("/ragflow-knowledge/register", response_model=ResourceVersionRecord, status_code=201)
async def register_ragflow_knowledge(request: RagflowDatasetRegister, principal: Principal = Depends(require_platform_admin)) -> ResourceVersionRecord:
    registry = get_resource_registry()
    connection = await registry.get_version(request.connection_version_id, principal, published=True)
    if connection.resource_type != ResourceType.KNOWLEDGE_CONNECTION:
        raise ApiError(422, "RESOURCE_TYPE_MISMATCH", "connection version is not a knowledge connection")
    datasets = await RagflowKnowledgeProvider(principal).discover_datasets(connection.config)
    dataset = next((item for item in datasets if item["id"] == request.dataset_id), None)
    if dataset is None:
        raise ApiError(409, "RAGFLOW_DATASET_NOT_DISCOVERED", "dataset must be discovered before registration")
    config = {
        "provider": "RAGFLOW",
        "connection_version_id": str(request.connection_version_id),
        "external_dataset_id": request.dataset_id,
        "external_dataset_name": dataset["name"],
        "external_dataset_description": dataset.get("description"),
    }
    definition = await registry.create_definition(ResourceDefinitionCreate(resource_type=ResourceType.KNOWLEDGE, slug=request.slug, display_name=request.display_name, description=request.description, draft_config=config), principal)
    version = await registry.create_version(definition.resource_id, ResourceVersionCreate(config=config), principal)
    published = await registry.publish_version(version.resource_version_id, principal)
    await discovery_snapshots.capture_published(published, principal)
    return published
