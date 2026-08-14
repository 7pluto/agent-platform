import asyncio
from uuid import uuid4

from app.control_plane.models import (
    AgentDefinitionCreate,
    AgentVersionCreate,
    DeploymentCreate,
    DeploymentRevisionCreate,
    VersionStatus,
)
from app.control_plane.store import ControlPlaneStore
from app.core.errors import ApiError
from app.iam.models import Principal
from app.resources.models import ModelDefinitionCreate, ModelVersionCreate
from app.resources.store import ResourceStore
from app.resources.registry_models import ResourceDefinitionCreate, ResourceType, ResourceVersionCreate
from app.resources.registry_store import ResourceRegistryStore


def _principal(tenant_id: str = "tenant-demo") -> Principal:
    return Principal(
        provider="mock",
        external_user_id="user-demo",
        external_org_id="org-demo",
        tenant_id=tenant_id,
        display_name="Demo User",
    )


def test_control_plane_publishes_immutable_version_and_activates_revision() -> None:
    async def run() -> None:
        store = ControlPlaneStore()
        principal = _principal()
        agent = await store.create_definition(
            AgentDefinitionCreate(slug="demo-agent", display_name="Demo", draft_spec={"prompt": "hello"}),
            principal,
        )
        version = await store.create_version(agent.agent_id, AgentVersionCreate(), principal)
        assert version.status == VersionStatus.DRAFT
        published = await store.publish_version(version.agent_version_id, principal)
        assert published.status == VersionStatus.PUBLISHED
        deployment = await store.create_deployment(
            DeploymentCreate(agent_id=agent.agent_id, name="demo-deployment"), principal
        )
        revision = await store.create_revision(
            deployment.deployment_id,
            DeploymentRevisionCreate(agent_version_id=published.agent_version_id, overrides={"temperature": 0}),
            principal,
        )
        active = await store.activate_revision(deployment.deployment_id, revision.deployment_revision_id, principal)
        resolved = await store.resolve(active.deployment_id, principal)
        assert resolved.revision.deployment_revision_id == revision.deployment_revision_id
        assert resolved.agent_version.content_hash == published.content_hash

        try:
            await store.publish_version(version.agent_version_id, principal)
        except ApiError as exc:
            assert exc.code == "VERSION_NOT_DRAFT"
        else:
            raise AssertionError("published version became mutable")

    asyncio.run(run())


def test_control_plane_rejects_cross_tenant_resolution() -> None:
    async def run() -> None:
        store = ControlPlaneStore()
        owner = _principal("tenant-a")
        agent = await store.create_definition(
            AgentDefinitionCreate(slug="tenant-agent", display_name="Tenant Agent"), owner
        )
        try:
            await store.create_version(agent.agent_id, AgentVersionCreate(), _principal("tenant-b"))
        except ApiError as exc:
            assert exc.code == "NOT_FOUND"
        else:
            raise AssertionError("cross-tenant Agent access was accepted")

        try:
            await store.create_deployment(DeploymentCreate(agent_id=uuid4(), name="bad-deployment"), owner)
        except ApiError as exc:
            assert exc.code == "NOT_FOUND"
        else:
            raise AssertionError("unknown Agent was accepted")

    asyncio.run(run())

def test_control_plane_lists_only_tenant_owned_resources() -> None:
    async def run() -> None:
        store = ControlPlaneStore()
        owner = _principal("tenant-a")
        other = _principal("tenant-b")
        agent = await store.create_definition(
            AgentDefinitionCreate(slug="listed-agent", display_name="Listed"), owner
        )
        version = await store.create_version(agent.agent_id, AgentVersionCreate(), owner)
        published = await store.publish_version(version.agent_version_id, owner)
        deployment = await store.create_deployment(
            DeploymentCreate(agent_id=agent.agent_id, name="listed-deployment"), owner
        )
        revision = await store.create_revision(
            deployment.deployment_id,
            DeploymentRevisionCreate(agent_version_id=published.agent_version_id),
            owner,
        )
        assert [item.agent_version_id for item in await store.list_versions(agent.agent_id, owner)] == [
            version.agent_version_id
        ]
        assert [item.deployment_id for item in await store.list_deployments(owner)] == [deployment.deployment_id]
        assert [item.deployment_revision_id for item in await store.list_revisions(deployment.deployment_id, owner)] == [
            revision.deployment_revision_id
        ]
        assert await store.list_deployments(other) == []

    asyncio.run(run())

def test_control_plane_rejects_secret_values_but_allows_secret_refs() -> None:
    async def run() -> None:
        store = ControlPlaneStore()
        principal = _principal()
        try:
            await store.create_definition(
                AgentDefinitionCreate(
                    slug="secret-agent", display_name="Secret", draft_spec={"provider": {"api_key": "plain"}}
                ),
                principal,
            )
        except ApiError as exc:
            assert exc.code == "SECRET_VALUE_FORBIDDEN"
        else:
            raise AssertionError("plain secret was accepted")

        agent = await store.create_definition(
            AgentDefinitionCreate(
                slug="secret-ref-agent",
                display_name="Secret ref",
                draft_spec={"provider": {"secret_ref": "secret://model/default"}},
            ),
            principal,
        )
        version = await store.create_version(agent.agent_id, AgentVersionCreate(), principal)
        assert version.specification["provider"]["secret_ref"] == "secret://model/default"

    asyncio.run(run())

def test_agent_version_requires_valid_builder_and_resource_references() -> None:
    async def run() -> None:
        store = ControlPlaneStore()
        principal = _principal()
        agent = await store.create_definition(AgentDefinitionCreate(slug="spec-agent", display_name="Spec"), principal)
        try:
            await store.create_version(agent.agent_id, AgentVersionCreate(specification={"builder": {"id": "unknown", "version": "1"}}), principal)
        except ApiError as exc:
            assert exc.code == "INVALID_BUILDER"
        else:
            raise AssertionError("unknown builder was accepted")
        version = await store.create_version(agent.agent_id, AgentVersionCreate(specification={"builder": {"id": "react", "version": "1"}, "model_ref": "model-version-1", "prompt_ref": "prompt-version-1"}), principal)
        assert version.specification["builder"]["id"] == "react"

    asyncio.run(run())


def test_v2_assembly_rejects_legacy_text_references() -> None:
    async def run() -> None:
        store = ControlPlaneStore()
        principal = _principal()
        agent = await store.create_definition(AgentDefinitionCreate(slug="v2-agent", display_name="V2"), principal)
        try:
            await store.create_version(agent.agent_id, AgentVersionCreate(specification={"assembly_schema": "v2", "prompt": {"system": "legacy"}}), principal)
        except ApiError as exc:
            assert exc.code == "LEGACY_RESOURCE_REFERENCE_FORBIDDEN"
        else:
            raise AssertionError("v2 Agent accepted a text prompt")

    asyncio.run(run())
