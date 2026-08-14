from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from urllib.parse import urlsplit
from uuid import UUID

from app.core.errors import ApiError
from app.core.secrets import reject_secret_values, validate_secret_ref
from app.iam.models import Principal
from app.resources.registry_models import (
    ResourceDefinitionCreate,
    ResourceDefinitionRecord,
    ResourceType,
    ResourceVersionCreate,
    ResourceVersionRecord,
    ResourceVersionStatus,
)


class ResourceRegistryStore:
    """In-memory registry used only by the local development storage mode."""

    def __init__(self) -> None:
        self._definitions: dict[UUID, ResourceDefinitionRecord] = {}
        self._versions: dict[UUID, ResourceVersionRecord] = {}
        self._lock = asyncio.Lock()

    async def create_definition(self, request: ResourceDefinitionCreate, principal: Principal) -> ResourceDefinitionRecord:
        self._validate(request.resource_type, request.draft_config)
        async with self._lock:
            if any(item.tenant_id == principal.tenant_id and item.resource_type == request.resource_type and item.slug == request.slug for item in self._definitions.values()):
                raise ApiError(409, "RESOURCE_SLUG_EXISTS", "resource type and slug already exist")
            record = ResourceDefinitionRecord(tenant_id=principal.tenant_id, created_by=principal.external_user_id, **request.model_dump())
            self._definitions[record.resource_id] = record
            return record.model_copy(deep=True)

    async def list_definitions(self, principal: Principal, resource_type: ResourceType | None = None) -> list[ResourceDefinitionRecord]:
        async with self._lock:
            return [item.model_copy(deep=True) for item in self._definitions.values() if item.tenant_id == principal.tenant_id and (resource_type is None or item.resource_type == resource_type)]

    async def create_version(self, resource_id: UUID, request: ResourceVersionCreate, principal: Principal) -> ResourceVersionRecord:
        async with self._lock:
            definition = self._definition(resource_id, principal)
            config = request.config or definition.draft_config
            self._validate(definition.resource_type, config)
            record = ResourceVersionRecord(resource_id=resource_id, tenant_id=principal.tenant_id, resource_type=definition.resource_type, version_number=1 + max((item.version_number for item in self._versions.values() if item.resource_id == resource_id), default=0), config=config, content_hash=self._hash(config), created_by=principal.external_user_id)
            self._versions[record.resource_version_id] = record
            return record.model_copy(deep=True)

    async def list_versions(self, resource_id: UUID, principal: Principal) -> list[ResourceVersionRecord]:
        async with self._lock:
            self._definition(resource_id, principal)
            return [item.model_copy(deep=True) for item in self._versions.values() if item.resource_id == resource_id and item.tenant_id == principal.tenant_id]

    async def list_published_versions(self, principal: Principal, resource_type: ResourceType | None = None) -> list[ResourceVersionRecord]:
        async with self._lock:
            return [item.model_copy(deep=True) for item in self._versions.values() if item.tenant_id == principal.tenant_id and item.status == ResourceVersionStatus.PUBLISHED and (resource_type is None or item.resource_type == resource_type)]

    async def get_version(self, resource_version_id: UUID, principal: Principal, published: bool = False) -> ResourceVersionRecord:
        async with self._lock:
            record = self._version(resource_version_id, principal)
            if published and record.status != ResourceVersionStatus.PUBLISHED:
                raise ApiError(409, "RESOURCE_VERSION_NOT_PUBLISHED", "resource version must be published")
            return record.model_copy(deep=True)

    async def publish_version(self, resource_version_id: UUID, principal: Principal) -> ResourceVersionRecord:
        async with self._lock:
            record = self._version(resource_version_id, principal)
            if record.status != ResourceVersionStatus.DRAFT:
                raise ApiError(409, "RESOURCE_VERSION_NOT_DRAFT", "only draft resource versions can be published")
            record = record.model_copy(update={"status": ResourceVersionStatus.PUBLISHED, "published_at": datetime.now(timezone.utc)})
            self._versions[resource_version_id] = record
            return record.model_copy(deep=True)

    def _definition(self, resource_id: UUID, principal: Principal) -> ResourceDefinitionRecord:
        value = self._definitions.get(resource_id)
        if value is None or value.tenant_id != principal.tenant_id:
            raise ApiError(404, "NOT_FOUND", "resource was not found")
        return value

    def _version(self, resource_version_id: UUID, principal: Principal) -> ResourceVersionRecord:
        value = self._versions.get(resource_version_id)
        if value is None or value.tenant_id != principal.tenant_id:
            raise ApiError(404, "NOT_FOUND", "resource version was not found")
        return value

    @staticmethod
    def _hash(config: dict) -> str:
        return hashlib.sha256(json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @staticmethod
    def _validate(resource_type: ResourceType, config: dict) -> None:
        reject_secret_values(config, f"resource.{resource_type.value}.config")
        if resource_type == ResourceType.PROMPT and not isinstance(config.get("template"), str):
            raise ApiError(422, "INVALID_PROMPT_CONFIG", "prompt config requires template")
        if resource_type == ResourceType.SKILL:
            if not isinstance(config.get("skill_md"), str) or not config["skill_md"].strip():
                raise ApiError(422, "INVALID_SKILL_CONFIG", "skill config requires skill_md")
            if not isinstance(config.get("tool_version_ids", []), list) or not isinstance(config.get("knowledge_version_ids", []), list):
                raise ApiError(422, "INVALID_SKILL_CONFIG", "skill dependencies must be lists")
        if resource_type == ResourceType.TOOL:
            if config.get("kind") == "NATIVE" and config.get("native_name") in {"current_time", "calculator", "echo"}:
                return
            if config.get("kind") == "MCP" and isinstance(config.get("connection_version_id"), str) and isinstance(config.get("tool_name"), str):
                return
            if config.get("kind") == "DIFY_FLOW":
                ResourceRegistryStore._validate_dify_flow(config)
                return
            if config.get("kind") == "HTTP":
                ResourceRegistryStore._validate_http_tool(config)
                return
            raise ApiError(422, "INVALID_TOOL_CONFIG", "tools must be registered NATIVE, discovered MCP, DIFY_FLOW, or governed HTTP")
        if resource_type == ResourceType.MCP_CONNECTION:
            endpoint = config.get("endpoint")
            if config.get("transport") != "streamable_http" or not isinstance(endpoint, str):
                raise ApiError(422, "INVALID_MCP_CONNECTION", "MCP connection requires streamable_http endpoint")
            parsed = urlsplit(endpoint)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
                raise ApiError(422, "INVALID_MCP_CONNECTION", "MCP endpoint must be an HTTP(S) URL without embedded credentials")
            allowlist = config.get("egress_allowlist")
            if not isinstance(allowlist, list) or not allowlist or not all(isinstance(host, str) and host.strip() for host in allowlist):
                raise ApiError(422, "INVALID_MCP_EGRESS_POLICY", "MCP connection requires a non-empty hostname egress_allowlist")
            allowed_hosts = {host.strip().lower().rstrip(".") for host in allowlist}
            if parsed.hostname.lower().rstrip(".") not in allowed_hosts:
                raise ApiError(422, "MCP_EGRESS_FORBIDDEN", "MCP endpoint hostname is not allowed by egress_allowlist")
            timeout = config.get("timeout_seconds", 10)
            if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0.1 <= float(timeout) <= 60:
                raise ApiError(422, "INVALID_MCP_CONNECTION", "MCP timeout_seconds must be between 0.1 and 60")
            secret_ref = config.get("secret_ref")
            if secret_ref is not None:
                if not isinstance(secret_ref, str):
                    raise ApiError(422, "INVALID_SECRET_REF", "MCP secret_ref must be a reference")
                validate_secret_ref(secret_ref)
                header = config.get("auth_header", "Authorization")
                scheme = config.get("auth_scheme", "Bearer")
                if not isinstance(header, str) or not header.strip() or not isinstance(scheme, str):
                    raise ApiError(422, "INVALID_MCP_CONNECTION", "MCP auth header and scheme are invalid")
        if resource_type == ResourceType.MEMORY_POLICY:
            if config.get("write_mode", "EXPLICIT") not in {"EXPLICIT", "POST_RUN_EXTRACT"}:
                raise ApiError(422, "INVALID_MEMORY_POLICY", "unsupported memory write mode")
            for field in ("read_enabled", "write_enabled"):
                if field in config and not isinstance(config[field], bool):
                    raise ApiError(422, "INVALID_MEMORY_POLICY", f"{field} must be boolean")
            ttl_days = config.get("ttl_days", 30)
            if isinstance(ttl_days, bool) or not isinstance(ttl_days, int) or not 1 <= ttl_days <= 3650:
                raise ApiError(422, "INVALID_MEMORY_POLICY", "ttl_days must be between 1 and 3650")
            max_items = config.get("max_items", 50)
            if isinstance(max_items, bool) or not isinstance(max_items, int) or not 1 <= max_items <= 1000:
                raise ApiError(422, "INVALID_MEMORY_POLICY", "max_items must be between 1 and 1000")
            categories = config.get("allowed_categories", [])
            if not isinstance(categories, list) or not all(isinstance(item, str) and item.strip() for item in categories):
                raise ApiError(422, "INVALID_MEMORY_POLICY", "allowed_categories must be a list of non-empty strings")
        if resource_type == ResourceType.KNOWLEDGE:
            if str(config.get("provider", "LOCAL")).upper() == "REMOTE_HTTP":
                ResourceRegistryStore._validate_remote_http_knowledge(config)
                return
            reference = config.get("embedding_model_version_id")
            if not isinstance(reference, str):
                raise ApiError(422, "EMBEDDING_MODEL_REQUIRED", "Knowledge requires embedding_model_version_id")
            try:
                UUID(reference)
            except ValueError as exc:
                raise ApiError(422, "INVALID_MODEL_REFERENCE", "embedding_model_version_id must be a UUID") from exc

    @staticmethod
    def _validate_remote_http_knowledge(config: dict) -> None:
        endpoint = config.get("endpoint")
        if not isinstance(endpoint, str):
            raise ApiError(422, "INVALID_REMOTE_KNOWLEDGE_CONFIG", "remote knowledge endpoint is required")
        parsed = urlsplit(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ApiError(422, "INVALID_REMOTE_KNOWLEDGE_CONFIG", "remote knowledge endpoint must be a clean HTTP(S) base URL")
        allowlist = config.get("egress_allowlist")
        if not isinstance(allowlist, list) or not allowlist or parsed.hostname.lower().rstrip(".") not in {str(item).lower().rstrip(".") for item in allowlist}:
            raise ApiError(422, "REMOTE_KNOWLEDGE_EGRESS_FORBIDDEN", "remote knowledge endpoint must be allowlisted")
        path = config.get("search_path", "/search")
        if not isinstance(path, str) or not path.startswith("/") or ".." in path or "://" in path or "?" in path or "#" in path:
            raise ApiError(422, "INVALID_REMOTE_KNOWLEDGE_CONFIG", "search_path must be a fixed absolute path")
        if config.get("method", "POST") not in {"GET", "POST"}:
            raise ApiError(422, "INVALID_REMOTE_KNOWLEDGE_CONFIG", "remote knowledge method must be GET or POST")
        mapping = config.get("response_mapping", {})
        if not isinstance(mapping, dict) or not isinstance(mapping.get("content_field", "content"), str):
            raise ApiError(422, "INVALID_REMOTE_KNOWLEDGE_CONFIG", "response_mapping must define content_field")
        secret_ref = config.get("secret_ref")
        if secret_ref is not None:
            if not isinstance(secret_ref, str):
                raise ApiError(422, "INVALID_SECRET_REF", "remote knowledge secret_ref must be a reference")
            validate_secret_ref(secret_ref)

    @staticmethod
    def _validate_dify_flow(config: dict) -> None:
        name = config.get("tool_name")
        if not isinstance(name, str) or not name or not name.replace("_", "a").isalnum() or len(name) > 64:
            raise ApiError(422, "INVALID_DIFY_FLOW_CONFIG", "tool_name must contain letters, numbers, or underscores")
        base_url = config.get("base_url")
        if not isinstance(base_url, str):
            raise ApiError(422, "INVALID_DIFY_FLOW_CONFIG", "base_url is required")
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ApiError(422, "INVALID_DIFY_FLOW_CONFIG", "base_url must be an HTTP(S) URL without embedded credentials")
        allowlist = config.get("egress_allowlist")
        if not isinstance(allowlist, list) or not allowlist or not all(isinstance(host, str) and host.strip() for host in allowlist):
            raise ApiError(422, "INVALID_DIFY_FLOW_CONFIG", "Dify Flow requires a non-empty egress_allowlist")
        allowed = {host.strip().lower().rstrip(".") for host in allowlist}
        if parsed.hostname.lower().rstrip(".") not in allowed:
            raise ApiError(422, "DIFY_FLOW_EGRESS_FORBIDDEN", "Dify Flow hostname is not allowed")
        if config.get("flow_type", "CHATFLOW") not in {"CHATFLOW", "WORKFLOW"}:
            raise ApiError(422, "INVALID_DIFY_FLOW_CONFIG", "flow_type must be CHATFLOW or WORKFLOW")
        secret_ref = config.get("secret_ref")
        if not isinstance(secret_ref, str):
            raise ApiError(422, "INVALID_DIFY_FLOW_CONFIG", "secret_ref is required")
        validate_secret_ref(secret_ref)
        timeout = config.get("timeout_seconds", 60)
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0.1 <= float(timeout) <= 300:
            raise ApiError(422, "INVALID_DIFY_FLOW_CONFIG", "timeout_seconds must be between 0.1 and 300")
        schema = config.get("input_schema", {"type": "object"})
        if not isinstance(schema, dict) or schema.get("type") != "object":
            raise ApiError(422, "INVALID_DIFY_FLOW_CONFIG", "input_schema must be a JSON object schema")

    @staticmethod
    def _validate_http_tool(config: dict) -> None:
        name = config.get("tool_name")
        if not isinstance(name, str) or not name or not name.replace("_", "a").isalnum() or len(name) > 64:
            raise ApiError(422, "INVALID_HTTP_TOOL_CONFIG", "tool_name must contain letters, numbers, or underscores")
        endpoint = config.get("endpoint")
        if not isinstance(endpoint, str):
            raise ApiError(422, "INVALID_HTTP_TOOL_CONFIG", "endpoint is required")
        parsed = urlsplit(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ApiError(422, "INVALID_HTTP_TOOL_CONFIG", "endpoint must be a clean HTTP(S) base URL without embedded credentials")
        allowlist = config.get("egress_allowlist")
        if not isinstance(allowlist, list) or not allowlist or not all(isinstance(host, str) and host.strip() for host in allowlist):
            raise ApiError(422, "INVALID_HTTP_EGRESS_POLICY", "HTTP Tool requires a non-empty hostname egress_allowlist")
        allowed = {host.strip().lower().rstrip(".") for host in allowlist}
        if parsed.hostname.lower().rstrip(".") not in allowed:
            raise ApiError(422, "HTTP_TOOL_EGRESS_FORBIDDEN", "HTTP Tool endpoint hostname is not allowed")
        if config.get("method", "GET") not in {"GET", "POST"}:
            raise ApiError(422, "INVALID_HTTP_TOOL_CONFIG", "HTTP Tool method must be GET or POST")
        path = config.get("path", "/")
        if not isinstance(path, str) or not path.startswith("/") or ".." in path or "://" in path or "?" in path or "#" in path:
            raise ApiError(422, "INVALID_HTTP_TOOL_CONFIG", "HTTP Tool path must be a fixed absolute path")
        timeout = config.get("timeout_seconds", 15)
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0.1 <= float(timeout) <= 60:
            raise ApiError(422, "INVALID_HTTP_TOOL_CONFIG", "timeout_seconds must be between 0.1 and 60")
        schema = config.get("input_schema", {"type": "object"})
        if not isinstance(schema, dict) or schema.get("type") != "object":
            raise ApiError(422, "INVALID_HTTP_TOOL_CONFIG", "input_schema must be a JSON object schema")
        for field in ("query_template", "body_template"):
            if field in config and not isinstance(config[field], (dict, list)):
                raise ApiError(422, "INVALID_HTTP_TOOL_CONFIG", f"{field} must be an object or array template")
        secret_ref = config.get("secret_ref")
        if secret_ref is not None:
            if not isinstance(secret_ref, str):
                raise ApiError(422, "INVALID_SECRET_REF", "HTTP Tool secret_ref must be a reference")
            validate_secret_ref(secret_ref)
            header = config.get("auth_header", "Authorization")
            scheme = config.get("auth_scheme", "Bearer")
            if not isinstance(header, str) or not header.strip() or not isinstance(scheme, str):
                raise ApiError(422, "INVALID_HTTP_TOOL_CONFIG", "HTTP Tool auth header and scheme are invalid")
