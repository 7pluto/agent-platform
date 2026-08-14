from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from uuid import UUID, uuid4

from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.errors import ApiError
from app.db.models import SecretVaultRow
from app.db.rls import set_local_tenant_context
from app.db.session import get_session_factory
from app.iam.models import Principal


_VAULT_REF = re.compile(r"^vault://([0-9a-fA-F-]{36})$")


class SecretCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    value: str = Field(min_length=1, max_length=32_768)


class SecretRotate(BaseModel):
    value: str = Field(min_length=1, max_length=32_768)


class SecretRecord(BaseModel):
    secret_ref: str
    name: str
    fingerprint: str
    status: str
    last_used_at: datetime | None = None
    rotated_at: datetime | None = None
    disabled_at: datetime | None = None
    created_by: str
    created_at: datetime


class SecretVault:
    def __init__(self) -> None:
        key = get_settings().secret_encryption_key
        if not key:
            raise ApiError(503, "SECRET_VAULT_NOT_CONFIGURED", "platform secret vault is not configured")
        try:
            self._fernet = Fernet(key.encode())
        except ValueError as exc:
            raise ApiError(503, "SECRET_VAULT_INVALID_KEY", "platform secret vault key is invalid") from exc

    async def create(self, name: str, value: str, principal: Principal) -> SecretRecord:
        if not value.strip():
            raise ApiError(422, "SECRET_VALUE_REQUIRED", "secret value is required")
        secret_id = uuid4()
        row = SecretVaultRow(
            secret_id=secret_id,
            tenant_id=principal.tenant_id,
            name=name[:128],
            encrypted_value=self._fernet.encrypt(value.encode()).decode(),
            fingerprint=hashlib.sha256(value.encode()).hexdigest(),
            status="ACTIVE",
            created_by=principal.external_user_id,
        )
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                session.add(row)
                await session.flush()
        return self._record(row)

    async def list(self, principal: Principal) -> list[SecretRecord]:
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                rows = await session.scalars(select(SecretVaultRow).where(SecretVaultRow.tenant_id == principal.tenant_id).order_by(SecretVaultRow.created_at.desc()))
                return [self._record(row) for row in rows.all()]

    async def rotate(self, secret_id: UUID, value: str, principal: Principal) -> SecretRecord:
        if not value.strip():
            raise ApiError(422, "SECRET_VALUE_REQUIRED", "secret value is required")
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                row = await session.get(SecretVaultRow, secret_id)
                if row is None or row.tenant_id != principal.tenant_id:
                    raise ApiError(404, "SECRET_NOT_FOUND", "secret was not found")
                if row.status != "ACTIVE":
                    raise ApiError(409, "SECRET_NOT_ACTIVE", "disabled secret cannot be rotated")
                row.encrypted_value = self._fernet.encrypt(value.encode()).decode()
                row.fingerprint = hashlib.sha256(value.encode()).hexdigest()
                row.rotated_at = datetime.now(timezone.utc)
                await session.flush()
                return self._record(row)

    async def disable(self, secret_id: UUID, principal: Principal) -> SecretRecord:
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, principal.tenant_id, principal.external_user_id)
                row = await session.get(SecretVaultRow, secret_id)
                if row is None or row.tenant_id != principal.tenant_id:
                    raise ApiError(404, "SECRET_NOT_FOUND", "secret was not found")
                if row.status == "DISABLED":
                    return self._record(row)
                row.status = "DISABLED"
                row.disabled_at = datetime.now(timezone.utc)
                await session.flush()
                return self._record(row)

    async def resolve(self, secret_ref: str, tenant_id: str, user_id: str) -> str:
        match = _VAULT_REF.fullmatch(secret_ref)
        if not match:
            raise ApiError(422, "INVALID_SECRET_REF", "secret reference must use vault://UUID")
        async with get_session_factory()() as session:
            async with session.begin():
                await set_local_tenant_context(session, tenant_id, user_id)
                row = await session.get(SecretVaultRow, UUID(match.group(1)))
                if row is None or row.tenant_id != tenant_id:
                    raise ApiError(404, "SECRET_NOT_FOUND", "referenced secret was not found")
                if row.status != "ACTIVE":
                    raise ApiError(409, "SECRET_DISABLED", "referenced secret is disabled")
                encrypted = row.encrypted_value
                row.last_used_at = datetime.now(timezone.utc)
        try:
            return self._fernet.decrypt(encrypted.encode()).decode()
        except InvalidToken as exc:
            raise ApiError(500, "SECRET_DECRYPTION_FAILED", "referenced secret cannot be decrypted") from exc

    @staticmethod
    def _record(row: SecretVaultRow) -> SecretRecord:
        return SecretRecord(
            secret_ref=f"vault://{row.secret_id}", name=row.name, fingerprint=row.fingerprint,
            status=row.status, last_used_at=row.last_used_at, rotated_at=row.rotated_at,
            disabled_at=row.disabled_at, created_by=row.created_by, created_at=row.created_at,
        )


def get_secret_vault() -> SecretVault:
    return SecretVault()
