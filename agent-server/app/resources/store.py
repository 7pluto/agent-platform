from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID

from app.core.errors import ApiError
from app.core.secrets import reject_secret_values
from app.iam.models import Principal
from app.resources.models import ModelAvailability, ModelConnectionTestResult, ModelDefinitionCreate, ModelDefinitionRecord, ModelVersionCreate, ModelVersionRecord, ResourceVersionStatus


class ResourceStore:
    """Tenant-safe in-memory resource registry for direct local development."""
    def __init__(self) -> None:
        self._models: dict[UUID, ModelDefinitionRecord] = {}
        self._versions: dict[UUID, ModelVersionRecord] = {}
        self._lock = asyncio.Lock()

    async def create_model(self, request: ModelDefinitionCreate, principal: Principal) -> ModelDefinitionRecord:
        reject_secret_values(request.config, "model.config")
        self._validate_config(request.config)
        async with self._lock:
            if any(item.tenant_id == principal.tenant_id and item.slug == request.slug for item in self._models.values()):
                raise ApiError(409, "MODEL_SLUG_EXISTS", "model slug already exists")
            record = ModelDefinitionRecord(tenant_id=principal.tenant_id, **request.model_dump())
            self._models[record.model_id] = record
            return record.model_copy(deep=True)

    async def list_models(self, principal: Principal) -> list[ModelDefinitionRecord]:
        async with self._lock:
            return [item.model_copy(deep=True) for item in self._models.values() if item.tenant_id == principal.tenant_id]

    async def create_model_version(self, model_id: UUID, request: ModelVersionCreate, principal: Principal) -> ModelVersionRecord:
        reject_secret_values(request.config, "model.version.config")
        async with self._lock:
            model = self._model(model_id, principal)
            config = request.config or model.config
            self._validate_config(config)
            record = ModelVersionRecord(model_id=model_id, tenant_id=principal.tenant_id, version_number=1 + max((item.version_number for item in self._versions.values() if item.model_id == model_id), default=0), provider=model.provider, config=config, content_hash=self._hash({"provider": model.provider, "config": config}))
            self._versions[record.model_version_id] = record
            return record.model_copy(deep=True)

    async def list_model_versions(self, model_id: UUID, principal: Principal) -> list[ModelVersionRecord]:
        async with self._lock:
            self._model(model_id, principal)
            return [item.model_copy(deep=True) for item in self._versions.values() if item.model_id == model_id and item.tenant_id == principal.tenant_id]

    async def get_model_version(self, identifier: UUID, principal: Principal, require_available: bool = False) -> ModelVersionRecord:
        async with self._lock:
            result = self._version(identifier, principal)
            if require_available and (result.status != ResourceVersionStatus.PUBLISHED or result.availability != ModelAvailability.AVAILABLE):
                raise ApiError(409, "MODEL_VERSION_NOT_AVAILABLE", "model version must be published and pass connection test")
            return result.model_copy(deep=True)

    async def record_connection_test(self, identifier: UUID, principal: Principal, available: bool, message: str) -> ModelConnectionTestResult:
        async with self._lock:
            record = self._version(identifier, principal)
            now = datetime.now(timezone.utc)
            record = record.model_copy(update={"availability": ModelAvailability.AVAILABLE if available else ModelAvailability.UNAVAILABLE, "last_tested_at": now, "last_test_error": None if available else message[:1000]})
            self._versions[identifier] = record
            return ModelConnectionTestResult(available=available, model_version_id=identifier, tested_at=now, message=message)

    async def publish_model_version(self, identifier: UUID, principal: Principal) -> ModelVersionRecord:
        async with self._lock:
            record = self._version(identifier, principal)
            if record.status != ResourceVersionStatus.DRAFT:
                raise ApiError(409, "MODEL_VERSION_NOT_DRAFT", "only draft model versions can be published")
            if record.availability != ModelAvailability.AVAILABLE:
                raise ApiError(409, "MODEL_CONNECTION_REQUIRED", "test the model connection successfully before publishing")
            record = record.model_copy(update={"status": ResourceVersionStatus.PUBLISHED, "published_at": datetime.now(timezone.utc)})
            self._versions[identifier] = record
            return record.model_copy(deep=True)

    @staticmethod
    def _validate_config(config: dict) -> None:
        from app.core.secrets import validate_persisted_secret_ref
        for key in ("base_url", "model", "secret_ref"):
            if not isinstance(config.get(key), str) or not config[key].strip():
                raise ApiError(422, "INVALID_MODEL_CONFIG", f"model config requires non-empty {key}")
        if not config["base_url"].startswith(("https://", "http://")):
            raise ApiError(422, "INVALID_MODEL_CONFIG", "base_url must be an HTTP(S) URL")
        validate_persisted_secret_ref(config["secret_ref"])

    def _model(self, identifier: UUID, principal: Principal) -> ModelDefinitionRecord:
        item = self._models.get(identifier)
        if item is None or item.tenant_id != principal.tenant_id:
            raise ApiError(404, "NOT_FOUND", "model was not found")
        return item

    def _version(self, identifier: UUID, principal: Principal) -> ModelVersionRecord:
        item = self._versions.get(identifier)
        if item is None or item.tenant_id != principal.tenant_id:
            raise ApiError(404, "NOT_FOUND", "model version was not found")
        return item

    @staticmethod
    def _hash(value: dict) -> str:
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
