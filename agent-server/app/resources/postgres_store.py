from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.secrets import reject_secret_values
from app.db.models import ModelDefinitionRow, ModelVersionRow
from app.db.rls import set_local_tenant_context
from app.db.session import get_session_factory
from app.iam.models import Principal
from app.resources.models import (
    ModelAvailability,
    ModelConnectionTestResult,
    ModelDefinitionCreate,
    ModelDefinitionRecord,
    ModelVersionCreate,
    ModelVersionRecord,
    ResourceVersionStatus,
)


class PostgresResourceStore:
    async def create_model(self, request: ModelDefinitionCreate, principal: Principal) -> ModelDefinitionRecord:
        reject_secret_values(request.config, "model.config")
        self._validate_config(request.config)
        async with self._session(principal) as session:
            async with session.begin():
                await self._context(session, principal)
                exists = await session.scalar(select(ModelDefinitionRow.model_id).where(ModelDefinitionRow.tenant_id == principal.tenant_id, ModelDefinitionRow.slug == request.slug))
                if exists:
                    raise ApiError(409, "MODEL_SLUG_EXISTS", "model slug already exists")
                row = ModelDefinitionRow(model_id=uuid4(), tenant_id=principal.tenant_id, **request.model_dump())
                session.add(row)
                await session.flush()
                return self._definition(row)

    async def list_models(self, principal: Principal) -> list[ModelDefinitionRecord]:
        async with self._session(principal) as session:
            async with session.begin():
                await self._context(session, principal)
                rows = await session.scalars(select(ModelDefinitionRow).where(ModelDefinitionRow.tenant_id == principal.tenant_id).order_by(ModelDefinitionRow.display_name, ModelDefinitionRow.model_id))
                return [self._definition(row) for row in rows]

    async def create_model_version(self, model_id: UUID, request: ModelVersionCreate, principal: Principal) -> ModelVersionRecord:
        reject_secret_values(request.config, "model.version.config")
        async with self._session(principal) as session:
            async with session.begin():
                await self._context(session, principal)
                model = await self._get_model(session, model_id, principal)
                config = request.config or model.config
                self._validate_config(config)
                number = await session.scalar(select(func.max(ModelVersionRow.version_number)).where(ModelVersionRow.tenant_id == principal.tenant_id, ModelVersionRow.model_id == model_id))
                row = ModelVersionRow(model_version_id=uuid4(), model_id=model_id, tenant_id=principal.tenant_id, version_number=(number or 0)+1, status=ResourceVersionStatus.DRAFT.value, provider=model.provider, config=config, content_hash=self._hash({"provider": model.provider, "config": config}), availability=ModelAvailability.UNKNOWN.value)
                session.add(row)
                await session.flush()
                return self._version(row)

    async def list_model_versions(self, model_id: UUID, principal: Principal) -> list[ModelVersionRecord]:
        async with self._session(principal) as session:
            async with session.begin():
                await self._context(session, principal)
                await self._get_model(session, model_id, principal)
                rows = await session.scalars(select(ModelVersionRow).where(ModelVersionRow.tenant_id == principal.tenant_id, ModelVersionRow.model_id == model_id).order_by(ModelVersionRow.version_number))
                return [self._version(row) for row in rows]

    async def get_model_version(self, model_version_id: UUID, principal: Principal, require_available: bool = False) -> ModelVersionRecord:
        async with self._session(principal) as session:
            async with session.begin():
                await self._context(session, principal)
                row = await self._get_version(session, model_version_id, principal)
                if require_available and (row.status != ResourceVersionStatus.PUBLISHED.value or row.availability != ModelAvailability.AVAILABLE.value):
                    raise ApiError(409, "MODEL_VERSION_NOT_AVAILABLE", "model version must be published and pass connection test")
                return self._version(row)

    async def publish_model_version(self, identifier: UUID, principal: Principal) -> ModelVersionRecord:
        async with self._session(principal) as session:
            async with session.begin():
                await self._context(session, principal)
                row = await self._get_version(session, identifier, principal, lock=True)
                if row.status != ResourceVersionStatus.DRAFT.value:
                    raise ApiError(409, "MODEL_VERSION_NOT_DRAFT", "only draft model versions can be published")
                if row.availability != ModelAvailability.AVAILABLE.value:
                    raise ApiError(409, "MODEL_CONNECTION_REQUIRED", "test the model connection successfully before publishing")
                row.status = ResourceVersionStatus.PUBLISHED.value
                row.published_at = datetime.now(timezone.utc)
                return self._version(row)

    async def record_connection_test(self, identifier: UUID, principal: Principal, available: bool, message: str) -> ModelConnectionTestResult:
        now = datetime.now(timezone.utc)
        async with self._session(principal) as session:
            async with session.begin():
                await self._context(session, principal)
                row = await self._get_version(session, identifier, principal, lock=True)
                row.availability = ModelAvailability.AVAILABLE.value if available else ModelAvailability.UNAVAILABLE.value
                row.last_tested_at = now
                row.last_test_error = None if available else message[:1000]
        return ModelConnectionTestResult(available=available, model_version_id=identifier, tested_at=now, message=message)

    @staticmethod
    def _validate_config(config: dict) -> None:
        from app.core.secrets import validate_persisted_secret_ref
        for key in ("base_url", "model", "secret_ref"):
            if not isinstance(config.get(key), str) or not config[key].strip():
                raise ApiError(422, "INVALID_MODEL_CONFIG", f"model config requires non-empty {key}")
        if not config["base_url"].startswith(("https://", "http://")):
            raise ApiError(422, "INVALID_MODEL_CONFIG", "base_url must be an HTTP(S) URL")
        validate_persisted_secret_ref(config["secret_ref"])

    @staticmethod
    def _hash(value: dict) -> str:
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @staticmethod
    async def _context(session: AsyncSession, principal: Principal) -> None:
        await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)

    @staticmethod
    def _session(principal: Principal):
        class TenantSession:
            async def __aenter__(self):
                self.session_context = get_session_factory()()
                return await self.session_context.__aenter__()
            async def __aexit__(self, *args):
                await self.session_context.__aexit__(*args)
        return TenantSession()

    @staticmethod
    async def _get_model(session: AsyncSession, identifier: UUID, principal: Principal) -> ModelDefinitionRow:
        row = await session.get(ModelDefinitionRow, identifier)
        if row is None or row.tenant_id != principal.tenant_id:
            raise ApiError(404, "NOT_FOUND", "model was not found")
        return row

    @staticmethod
    async def _get_version(session: AsyncSession, identifier: UUID, principal: Principal, lock: bool = False) -> ModelVersionRow:
        row = await (session.scalar(select(ModelVersionRow).where(ModelVersionRow.model_version_id == identifier).with_for_update()) if lock else session.get(ModelVersionRow, identifier))
        if row is None or row.tenant_id != principal.tenant_id:
            raise ApiError(404, "NOT_FOUND", "model version was not found")
        return row

    @staticmethod
    def _definition(row: ModelDefinitionRow) -> ModelDefinitionRecord:
        return ModelDefinitionRecord(model_id=row.model_id, tenant_id=row.tenant_id, slug=row.slug, display_name=row.display_name, provider=row.provider, config=row.config, created_at=row.created_at)

    @staticmethod
    def _version(row: ModelVersionRow) -> ModelVersionRecord:
        return ModelVersionRecord(model_version_id=row.model_version_id, model_id=row.model_id, tenant_id=row.tenant_id, version_number=row.version_number, status=ResourceVersionStatus(row.status), provider=row.provider, config=row.config, content_hash=row.content_hash, created_at=row.created_at, published_at=row.published_at, availability=ModelAvailability(row.availability), last_tested_at=row.last_tested_at, last_test_error=row.last_test_error)
