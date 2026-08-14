from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet, InvalidToken

from app.config import Settings
from app.iam.models import Principal
from app.iam.providers import UpstreamToken


@dataclass
class SessionRecord:
    session_id_hash: str
    encrypted_upstream_token: str
    principal: Principal
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    csrf_token: str

    def to_payload(self) -> dict:
        return {
            "session_id_hash": self.session_id_hash,
            "encrypted_upstream_token": self.encrypted_upstream_token,
            "principal": self.principal.model_dump(mode="json"),
            "created_at": self.created_at.isoformat(),
            "last_seen_at": self.last_seen_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "csrf_token": self.csrf_token,
        }

    @classmethod
    def from_payload(cls, payload: dict) -> "SessionRecord":
        return cls(
            session_id_hash=payload["session_id_hash"],
            encrypted_upstream_token=payload["encrypted_upstream_token"],
            principal=Principal.model_validate(payload["principal"]),
            created_at=datetime.fromisoformat(payload["created_at"]),
            last_seen_at=datetime.fromisoformat(payload["last_seen_at"]),
            expires_at=datetime.fromisoformat(payload["expires_at"]),
            csrf_token=payload["csrf_token"],
        )


class SessionStore:
    """Development in-memory BFF session store with the shared async contract."""

    def __init__(self, settings: Settings) -> None:
        key = settings.session_encryption_key or Fernet.generate_key().decode()
        self._fernet = Fernet(key.encode())
        self._idle = timedelta(minutes=settings.session_idle_minutes)
        self._absolute = timedelta(hours=settings.session_absolute_hours)
        self._records: dict[str, SessionRecord] = {}

    @staticmethod
    def session_hash(session_id: str) -> str:
        return hashlib.sha256(session_id.encode()).hexdigest()

    def new_record(self, token: UpstreamToken, principal: Principal) -> tuple[str, SessionRecord]:
        now = datetime.now(timezone.utc)
        session_id = secrets.token_urlsafe(32)
        record = SessionRecord(
            session_id_hash=self.session_hash(session_id),
            encrypted_upstream_token=self._fernet.encrypt(token.value.encode()).decode(),
            principal=principal,
            created_at=now,
            last_seen_at=now,
            expires_at=now + self._absolute,
            csrf_token=secrets.token_urlsafe(32),
        )
        return session_id, record

    async def create(self, token: UpstreamToken, principal: Principal) -> tuple[str, SessionRecord]:
        session_id, record = self.new_record(token, principal)
        self._records[record.session_id_hash] = record
        return session_id, record

    async def get(self, session_id: str) -> SessionRecord | None:
        record = self._records.get(self.session_hash(session_id))
        if not record:
            return None
        now = datetime.now(timezone.utc)
        if now >= record.expires_at or now - record.last_seen_at > self._idle:
            await self.delete(session_id)
            return None
        record.last_seen_at = now
        return record

    async def update_principal(self, record: SessionRecord) -> None:
        self._records[record.session_id_hash] = record

    async def upstream_token(self, record: SessionRecord) -> UpstreamToken:
        try:
            return UpstreamToken(self._fernet.decrypt(record.encrypted_upstream_token.encode()).decode())
        except InvalidToken as exc:
            raise RuntimeError("session upstream token cannot be decrypted") from exc

    async def delete(self, session_id: str) -> None:
        self._records.pop(self.session_hash(session_id), None)

    async def close(self) -> None:
        return None

    @property
    def idle_seconds(self) -> int:
        return int(self._idle.total_seconds())

    def remaining_ttl_seconds(self, record: SessionRecord, now: datetime) -> int:
        return max(1, min(self.idle_seconds, int((record.expires_at - now).total_seconds())))