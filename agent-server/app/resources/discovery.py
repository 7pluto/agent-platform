"""Immutable discovery snapshots and provider drift reconciliation."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import desc, select

from app.config import get_settings
from app.core.errors import ApiError
from app.db.models import ResourceDiscoverySnapshotRow
from app.db.rls import set_local_tenant_context
from app.db.session import get_session_factory
from app.iam.models import Principal
from app.knowledge.providers.ragflow import RagflowKnowledgeProvider
from app.resources.providers.registry import provider_registry
from app.resources.registry_factory import get_resource_registry
from app.resources.registry_models import (
    DiscoveryDriftStatus,
    ResourceDiscoverySnapshotRecord,
    ResourceDriftReport,
    ResourceType,
    ResourceVersionCreate,
    ResourceVersionRecord,
    ResourceVersionStatus,
)
from app.resources.registry_store import ResourceRegistryStore
from app.resources.validation import redact_validation_result


def _canonical_hash(value: dict[str, Any]) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _dify_input_schema(flow_type: str, input_form: list[Any]) -> dict[str, Any]:
    type_map = {
        "text-input": "string", "paragraph": "string", "select": "string",
        "number": "number", "checkbox": "boolean",
    }
    properties: dict[str, dict[str, Any]] = {}
    required: list[str] = []
    for wrapper in input_form:
        if not isinstance(wrapper, dict) or not wrapper:
            continue
        kind, definition = next(iter(wrapper.items()))
        if not isinstance(definition, dict):
            continue
        variable = str(definition.get("variable", "")).strip()
        if not variable:
            continue
        field: dict[str, Any] = {
            "type": type_map.get(str(kind), "string"),
            "description": str(definition.get("label") or variable),
        }
        options = definition.get("options")
        if isinstance(options, list) and all(isinstance(item, str) for item in options):
            field["enum"] = options
        properties[variable] = field
        if definition.get("required") is True:
            required.append(variable)
    inputs: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        inputs["required"] = required
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "用户当前的业务问题"},
            "inputs": {**inputs, "description": "Dify 应用公开的结构化输入变量"},
        },
    }
    if flow_type == "CHATFLOW":
        schema["required"] = ["query"]
    elif required:
        schema["required"] = ["inputs"]
    return schema


def _published_shape(record: ResourceVersionRecord) -> tuple[str, str, str, dict[str, Any]] | None:
    config = record.config
    if record.resource_type == ResourceType.TOOL and config.get("kind") == "DIFY_FLOW":
        shape = {
            "flow_type": str(config.get("flow_type", "CHATFLOW")),
            "input_form": config.get("dify_input_form", []),
        }
        return "DIFY", "APPLICATION", str(config.get("tool_name", "")), shape
    if record.resource_type == ResourceType.TOOL and config.get("kind") == "MCP":
        shape = {
            "tool_name": str(config.get("tool_name", "")),
            "description": config.get("description"),
            "input_schema": config.get("input_schema", {}),
        }
        return "MCP", "TOOL", shape["tool_name"], shape
    if record.resource_type == ResourceType.TOOL and config.get("kind") == "HTTP":
        shape = {
            "tool_name": str(config.get("tool_name", "")),
            "method": str(config.get("method", "GET")),
            "path": str(config.get("path", "/")),
            "input_schema": config.get("input_schema", {}),
            "request_mapping": {
                "query_template": config.get("query_template"),
                "body_template": config.get("body_template"),
            },
        }
        return "HTTP", "TOOL", shape["tool_name"], shape
    if record.resource_type == ResourceType.KNOWLEDGE and str(config.get("provider", "LOCAL")).upper() == "RAGFLOW":
        shape = {
            "dataset_id": str(config.get("external_dataset_id", "")),
            "dataset_name": str(config.get("external_dataset_name", "")),
            "description": config.get("external_dataset_description"),
        }
        return "RAGFLOW", "DATASET", shape["dataset_id"], shape
    return None


class ResourceDiscoveryService:
    def __init__(self, registry=None) -> None:
        self.registry = registry or get_resource_registry()
        self._memory: dict[tuple[str, UUID], ResourceDiscoverySnapshotRecord] = {}

    async def capture_published(
        self, record: ResourceVersionRecord, principal: Principal,
    ) -> ResourceDiscoverySnapshotRecord | None:
        if record.status != ResourceVersionStatus.PUBLISHED:
            raise ApiError(409, "RESOURCE_VERSION_NOT_PUBLISHED", "discovery snapshots require a published version")
        shaped = _published_shape(record)
        if shaped is None:
            return None
        existing = await self.latest(record.resource_version_id, principal)
        if existing is not None:
            return existing
        provider, external_type, external_id, snapshot = shaped
        safe_snapshot = redact_validation_result(snapshot)
        record_snapshot = ResourceDiscoverySnapshotRecord(
            snapshot_id=uuid4(), tenant_id=principal.tenant_id,
            resource_version_id=record.resource_version_id, provider=provider,
            external_type=external_type, external_id=external_id,
            schema_hash=_canonical_hash(snapshot), snapshot=safe_snapshot,
            created_by=principal.external_user_id, created_at=datetime.now(timezone.utc),
        )
        if get_settings().storage_mode != "postgres":
            self._memory[(principal.tenant_id, record.resource_version_id)] = record_snapshot
            return record_snapshot
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                session.add(ResourceDiscoverySnapshotRow(**record_snapshot.model_dump()))
        return record_snapshot

    async def latest(
        self, resource_version_id: UUID, principal: Principal,
    ) -> ResourceDiscoverySnapshotRecord | None:
        if get_settings().storage_mode != "postgres":
            return self._memory.get((principal.tenant_id, resource_version_id))
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                row = await session.scalar(select(ResourceDiscoverySnapshotRow).where(
                    ResourceDiscoverySnapshotRow.tenant_id == principal.tenant_id,
                    ResourceDiscoverySnapshotRow.resource_version_id == resource_version_id,
                ).order_by(desc(ResourceDiscoverySnapshotRow.created_at)))
        return ResourceDiscoverySnapshotRecord.model_validate(row, from_attributes=True) if row else None

    async def list(
        self, resource_version_id: UUID, principal: Principal,
    ) -> list[ResourceDiscoverySnapshotRecord]:
        item = await self.latest(resource_version_id, principal)
        return [item] if item else []

    async def check_drift(
        self, record: ResourceVersionRecord, principal: Principal, *, create_draft: bool = True,
    ) -> ResourceDriftReport:
        snapshot = await self.latest(record.resource_version_id, principal)
        if snapshot is None:
            snapshot = await self.capture_published(record, principal)
        if snapshot is None:
            raise ApiError(422, "DISCOVERY_NOT_SUPPORTED", "resource does not support discovery drift")
        try:
            current, updated_config = await self._discover_current(record, principal)
        except ApiError as exc:
            return ResourceDriftReport(
                resource_version_id=record.resource_version_id, provider=snapshot.provider,
                status=DiscoveryDriftStatus.UNAVAILABLE,
                published_schema_hash=snapshot.schema_hash,
                message=f"{exc.code}: {exc.message}",
            )
        if current is None:
            return ResourceDriftReport(
                resource_version_id=record.resource_version_id, provider=snapshot.provider,
                status=DiscoveryDriftStatus.MISSING,
                published_schema_hash=snapshot.schema_hash,
                message="published provider object is no longer discoverable",
            )
        current_hash = _canonical_hash(current)
        status = DiscoveryDriftStatus.NO_CHANGE if current_hash == snapshot.schema_hash else DiscoveryDriftStatus.CHANGED
        draft_id = None
        if status == DiscoveryDriftStatus.CHANGED and create_draft and updated_config is not None:
            draft_id = await self._ensure_draft(record, updated_config, principal)
        return ResourceDriftReport(
            resource_version_id=record.resource_version_id, provider=snapshot.provider,
            status=status, published_schema_hash=snapshot.schema_hash,
            current_schema_hash=current_hash, current_snapshot=redact_validation_result(current),
            draft_version_id=draft_id,
        )

    async def _discover_current(
        self, record: ResourceVersionRecord, principal: Principal,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        config = record.config
        if record.resource_type == ResourceType.TOOL and config.get("kind") == "DIFY_FLOW":
            result = await provider_registry.resolve(record.resource_type, config, principal).discover(config)
            if not result.ok:
                raise ApiError(502, str(result.error_code or "UPSTREAM_ERROR"), result.message or "Dify discovery failed")
            input_form = [item["definition"] for item in result.items if isinstance(item, dict) and isinstance(item.get("definition"), dict)]
            flow_type = str(config.get("flow_type", "CHATFLOW"))
            current = {"flow_type": flow_type, "input_form": input_form}
            updated = {**config, "dify_input_form": input_form, "input_schema": _dify_input_schema(flow_type, input_form)}
            return current, updated
        if record.resource_type == ResourceType.TOOL and config.get("kind") == "MCP":
            connection = await self.registry.get_version(UUID(str(config["connection_version_id"])), principal, published=True)
            result = await provider_registry.resolve(connection.resource_type, connection.config, principal).discover(connection.config)
            if not result.ok:
                raise ApiError(502, str(result.error_code or "UPSTREAM_ERROR"), result.message or "MCP discovery failed")
            tool = next((item for item in result.items if str(item.get("name")) == str(config.get("tool_name"))), None)
            if tool is None:
                return None, None
            current = {
                "tool_name": str(tool.get("name", "")),
                "description": tool.get("description"),
                "input_schema": tool.get("inputSchema", {}),
            }
            updated = {**config, "description": tool.get("description"), "input_schema": tool.get("inputSchema", {})}
            return current, updated
        if record.resource_type == ResourceType.KNOWLEDGE and str(config.get("provider", "")).upper() == "RAGFLOW":
            connection = await self.registry.get_version(UUID(str(config["connection_version_id"])), principal, published=True)
            datasets = await RagflowKnowledgeProvider(principal).discover_datasets(connection.config)
            dataset = next((item for item in datasets if str(item.get("id")) == str(config.get("external_dataset_id"))), None)
            if dataset is None:
                return None, None
            current = {
                "dataset_id": str(dataset.get("id", "")),
                "dataset_name": str(dataset.get("name", "")),
                "description": dataset.get("description"),
            }
            updated = {
                **config,
                "external_dataset_name": current["dataset_name"],
                "external_dataset_description": current["description"],
            }
            return current, updated
        if record.resource_type == ResourceType.TOOL and config.get("kind") == "HTTP":
            shaped = _published_shape(record)
            return (shaped[3], None) if shaped else (None, None)
        raise ApiError(422, "DISCOVERY_NOT_SUPPORTED", "resource does not support discovery drift")

    async def _ensure_draft(
        self, record: ResourceVersionRecord, config: dict[str, Any], principal: Principal,
    ) -> UUID:
        content_hash = ResourceRegistryStore._hash(config)
        for version in await self.registry.list_versions(record.resource_id, principal):
            if version.status == ResourceVersionStatus.DRAFT and version.content_hash == content_hash:
                return version.resource_version_id
        draft = await self.registry.create_version(record.resource_id, ResourceVersionCreate(config=config), principal)
        return draft.resource_version_id


_service = ResourceDiscoveryService()


def get_resource_discovery_service() -> ResourceDiscoveryService:
    return _service
