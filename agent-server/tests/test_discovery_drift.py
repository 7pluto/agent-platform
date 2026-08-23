from uuid import UUID, uuid4

import pytest

import app.resources.discovery as discovery_module
from app.iam.models import Principal
from app.resources.discovery import ResourceDiscoveryService
from app.resources.providers.base import DiscoveryResult
from app.resources.registry_models import (
    DiscoveryDriftStatus,
    ResourceType,
    ResourceVersionRecord,
    ResourceVersionStatus,
)
from app.resources.registry_store import ResourceRegistryStore


def _principal() -> Principal:
    return Principal(
        provider="mock", external_user_id="developer", external_org_id="org",
        tenant_id="tenant", display_name="Developer",
    )


def _published(config: dict, resource_type: ResourceType = ResourceType.TOOL) -> ResourceVersionRecord:
    return ResourceVersionRecord(
        resource_version_id=uuid4(), resource_id=uuid4(), tenant_id="tenant",
        resource_type=resource_type, version_number=1, status=ResourceVersionStatus.PUBLISHED,
        config=config, content_hash=ResourceRegistryStore._hash(config), created_by="developer",
    )


class _FakeRegistry:
    def __init__(self, published: ResourceVersionRecord) -> None:
        self.versions = [published]

    async def list_versions(self, resource_id: UUID, principal: Principal) -> list[ResourceVersionRecord]:
        return [item for item in self.versions if item.resource_id == resource_id]

    async def create_version(self, resource_id: UUID, request, principal: Principal) -> ResourceVersionRecord:
        record = ResourceVersionRecord(
            resource_version_id=uuid4(), resource_id=resource_id, tenant_id=principal.tenant_id,
            resource_type=self.versions[0].resource_type, version_number=len(self.versions) + 1,
            status=ResourceVersionStatus.DRAFT, config=request.config,
            content_hash=ResourceRegistryStore._hash(request.config), created_by=principal.external_user_id,
        )
        self.versions.append(record)
        return record


class _ChangedDifyProvider:
    async def discover(self, config: dict) -> DiscoveryResult:
        return DiscoveryResult(
            provider="DIFY", ok=True,
            items=[{
                "kind": "INPUT",
                "definition": {"text-input": {"variable": "department", "label": "部门", "required": True}},
            }],
        )


@pytest.mark.asyncio
async def test_changed_dify_snapshot_creates_one_immutable_draft(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(discovery_module, "get_settings", lambda: type("Settings", (), {"storage_mode": "memory"})())
    monkeypatch.setattr(discovery_module.provider_registry, "resolve", lambda *args: _ChangedDifyProvider())
    published = _published({
        "kind": "DIFY_FLOW", "tool_name": "policy_flow", "flow_type": "CHATFLOW",
        "dify_input_form": [], "input_schema": {"type": "object"},
        "base_url": "https://dify.example.com", "secret_ref": "vault://00000000-0000-0000-0000-000000000001",
    })
    registry = _FakeRegistry(published)
    service = ResourceDiscoveryService(registry)

    snapshot = await service.capture_published(published, _principal())
    report = await service.check_drift(published, _principal())
    repeated = await service.check_drift(published, _principal())

    assert snapshot is not None
    assert snapshot.provider == "DIFY"
    assert "secret_ref" not in snapshot.snapshot
    assert report.status == DiscoveryDriftStatus.CHANGED
    assert report.draft_version_id is not None
    assert repeated.draft_version_id == report.draft_version_id
    assert len(registry.versions) == 2
    assert registry.versions[-1].status == ResourceVersionStatus.DRAFT
    assert registry.versions[-1].config["input_schema"]["properties"]["inputs"]["required"] == ["department"]


@pytest.mark.asyncio
async def test_governed_http_snapshot_reports_no_change(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(discovery_module, "get_settings", lambda: type("Settings", (), {"storage_mode": "memory"})())
    published = _published({
        "kind": "HTTP", "tool_name": "ticket_query", "endpoint": "https://api.example.com",
        "path": "/tickets/{{ticket_id}}", "method": "GET",
        "input_schema": {"type": "object", "properties": {"ticket_id": {"type": "string"}}},
        "query_template": {"include_history": True}, "egress_allowlist": ["api.example.com"],
    })
    service = ResourceDiscoveryService(_FakeRegistry(published))

    snapshot = await service.capture_published(published, _principal())
    report = await service.check_drift(published, _principal())

    assert snapshot is not None
    assert snapshot.provider == "HTTP"
    assert report.status == DiscoveryDriftStatus.NO_CHANGE
    assert report.current_schema_hash == snapshot.schema_hash
    assert report.draft_version_id is None
