from uuid import uuid4

import pytest

import app.control_plane.validation as validation_module
from app.control_plane.assembly import ResolvedAssemblyResource
from app.control_plane.validation import AgentValidationService
from app.iam.models import Principal
from app.resources.registry_models import (
    DiscoveryDriftStatus,
    ResourceDriftReport,
    ResourceType,
    ResourceVersionRecord,
    ResourceVersionStatus,
)
from app.resources.registry_store import ResourceRegistryStore


def _principal() -> Principal:
    return Principal(
        provider="mock", external_user_id="admin", external_org_id="org",
        tenant_id="tenant", display_name="Admin",
    )


def _knowledge(provider: str) -> ResourceVersionRecord:
    config = {"provider": provider}
    if provider == "RAGFLOW":
        config.update({
            "connection_version_id": str(uuid4()), "external_dataset_id": "dataset-1",
            "external_dataset_name": "装维制度",
        })
    return ResourceVersionRecord(
        resource_version_id=uuid4(), resource_id=uuid4(), tenant_id="tenant",
        resource_type=ResourceType.KNOWLEDGE, version_number=1,
        status=ResourceVersionStatus.PUBLISHED, config=config,
        content_hash=ResourceRegistryStore._hash(config), created_by="admin",
    )


class _SuccessfulTests:
    async def has_successful_validation(self, *args, **kwargs) -> bool:
        return True


class _MissingRagflow:
    async def check_drift(self, resource, principal, create_draft=False) -> ResourceDriftReport:
        return ResourceDriftReport(
            resource_version_id=resource.resource_version_id, provider="RAGFLOW",
            status=DiscoveryDriftStatus.MISSING, published_schema_hash="a" * 64,
            message="published provider object is no longer discoverable",
        )


@pytest.mark.asyncio
async def test_remote_http_knowledge_uses_provider_test_not_local_index(monkeypatch: pytest.MonkeyPatch) -> None:
    resource = _knowledge("REMOTE_HTTP")
    async def resolved(*args, **kwargs):
        return [ResolvedAssemblyResource(resource, "DIRECT", ["agent.knowledge"])]
    monkeypatch.setattr(validation_module, "resolve_agent_assembly", resolved)
    monkeypatch.setattr(validation_module, "get_resource_validation_service", lambda: _SuccessfulTests())
    monkeypatch.setattr(validation_module, "get_settings", lambda: type("Settings", (), {"storage_mode": "memory"})())

    outcome = await AgentValidationService().validate({"assembly_schema": "v2"}, _principal())

    assert outcome.valid
    assert not any(item["code"] == "KNOWLEDGE_INDEX_NOT_ACTIVE" for item in outcome.blocking_errors)


@pytest.mark.asyncio
async def test_missing_ragflow_dataset_blocks_agent_publish(monkeypatch: pytest.MonkeyPatch) -> None:
    resource = _knowledge("RAGFLOW")
    async def resolved(*args, **kwargs):
        return [ResolvedAssemblyResource(resource, "DIRECT", ["agent.knowledge"])]
    monkeypatch.setattr(validation_module, "resolve_agent_assembly", resolved)
    monkeypatch.setattr(validation_module, "get_resource_validation_service", lambda: _SuccessfulTests())
    monkeypatch.setattr(validation_module, "get_resource_discovery_service", lambda: _MissingRagflow())
    monkeypatch.setattr(validation_module, "get_settings", lambda: type("Settings", (), {"storage_mode": "memory"})())

    outcome = await AgentValidationService().validate({"assembly_schema": "v2"}, _principal())

    assert not outcome.valid
    assert any(item["code"] == "RAGFLOW_MISSING" for item in outcome.blocking_errors)
