from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.dependencies import require_fresh_principal, require_platform_admin
from app.control_plane.models import (
    AgentDefinitionCreate,
    AgentDefinitionRecord,
    AgentVersionCreate,
    AgentVersionRecord,
    DeploymentCreate,
    DeploymentRecord,
    DeploymentRevisionCreate,
    DeploymentRevisionRecord,
    ResolvedDeployment,
)
from app.control_plane.store_factory import get_control_plane_store
from app.governance.store_factory import get_governance_store
from app.iam.models import Principal

router = APIRouter(tags=["control-plane"])
store = get_control_plane_store()
governance_store = get_governance_store()


@router.post("/agents", response_model=AgentDefinitionRecord, status_code=201)
async def create_agent(
    request: AgentDefinitionCreate,
    principal: Principal = Depends(require_platform_admin),
) -> AgentDefinitionRecord:
    record = await store.create_definition(request, principal)
    await governance_store.record_audit(principal, "agent.create", "AGENT_DEFINITION", str(record.agent_id), {"slug": record.slug})
    return record


@router.get("/agents", response_model=list[AgentDefinitionRecord])
async def list_agents(principal: Principal = Depends(require_fresh_principal)) -> list[AgentDefinitionRecord]:
    return await store.list_definitions(principal)


@router.get("/agents/{agent_id}/versions", response_model=list[AgentVersionRecord])
async def list_agent_versions(
    agent_id: UUID, principal: Principal = Depends(require_fresh_principal)
) -> list[AgentVersionRecord]:
    return await store.list_versions(agent_id, principal)
@router.post("/agents/{agent_id}/versions", response_model=AgentVersionRecord, status_code=201)
async def create_agent_version(
    agent_id: UUID,
    request: AgentVersionCreate,
    principal: Principal = Depends(require_platform_admin),
) -> AgentVersionRecord:
    record = await store.create_version(agent_id, request, principal)
    await governance_store.record_audit(
        principal,
        "agent_version.create",
        "AGENT_VERSION",
        str(record.agent_version_id),
        {"agent_id": str(agent_id), "version_number": record.version_number},
    )
    return record


@router.post("/agent-versions/{agent_version_id}/publish", response_model=AgentVersionRecord)
async def publish_agent_version(
    agent_version_id: UUID,
    principal: Principal = Depends(require_platform_admin),
) -> AgentVersionRecord:
    record = await store.publish_version(agent_version_id, principal)
    await governance_store.record_audit(
        principal,
        "agent_version.publish",
        "AGENT_VERSION",
        str(record.agent_version_id),
        {"content_hash": record.content_hash},
    )
    return record


@router.get("/deployments", response_model=list[DeploymentRecord])
async def list_deployments(principal: Principal = Depends(require_fresh_principal)) -> list[DeploymentRecord]:
    return await store.list_deployments(principal)
@router.post("/deployments", response_model=DeploymentRecord, status_code=201)
async def create_deployment(
    request: DeploymentCreate,
    principal: Principal = Depends(require_platform_admin),
) -> DeploymentRecord:
    record = await store.create_deployment(request, principal)
    await governance_store.record_audit(
        principal,
        "deployment.create",
        "DEPLOYMENT",
        str(record.deployment_id),
        {"name": record.name, "agent_id": str(record.agent_id)},
    )
    return record


@router.get("/deployments/{deployment_id}/revisions", response_model=list[DeploymentRevisionRecord])
async def list_deployment_revisions(
    deployment_id: UUID, principal: Principal = Depends(require_fresh_principal)
) -> list[DeploymentRevisionRecord]:
    return await store.list_revisions(deployment_id, principal)
@router.post("/deployments/{deployment_id}/revisions", response_model=DeploymentRevisionRecord, status_code=201)
async def create_deployment_revision(
    deployment_id: UUID,
    request: DeploymentRevisionCreate,
    principal: Principal = Depends(require_platform_admin),
) -> DeploymentRevisionRecord:
    record = await store.create_revision(deployment_id, request, principal)
    await governance_store.record_audit(
        principal,
        "deployment_revision.create",
        "DEPLOYMENT_REVISION",
        str(record.deployment_revision_id),
        {"deployment_id": str(deployment_id), "revision_number": record.revision_number},
    )
    return record


@router.post("/deployments/{deployment_id}/revisions/{revision_id}/activate", response_model=DeploymentRecord)
async def activate_deployment_revision(
    deployment_id: UUID,
    revision_id: UUID,
    principal: Principal = Depends(require_platform_admin),
) -> DeploymentRecord:
    record = await store.activate_revision(deployment_id, revision_id, principal)
    await governance_store.record_audit(
        principal,
        "deployment_revision.activate",
        "DEPLOYMENT",
        str(record.deployment_id),
        {"revision_id": str(revision_id)},
    )
    return record


@router.get("/deployments/{deployment_id}/resolve", response_model=ResolvedDeployment)
async def resolve_deployment(
    deployment_id: UUID,
    principal: Principal = Depends(require_fresh_principal),
) -> ResolvedDeployment:
    return await store.resolve(deployment_id, principal)