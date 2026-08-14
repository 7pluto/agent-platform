from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.config import Settings
from app.iam.models import Principal
from app.iam.providers import UpstreamToken
from app.session.store import SessionRecord, SessionStore


class RedisSessionStore(SessionStore):
    """Redis-backed BFF session store; browser cookies never carry upstream tokens."""

    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        super().__init__(settings)
        self._prefix = settings.redis_session_key_prefix
        if client is None:
            try:
                import redis.asyncio as redis
            except ImportError as exc:
                raise RuntimeError("redis package is required for AGENT_SESSION_STORAGE_MODE=redis") from exc
            client = redis.from_url(settings.redis_url, decode_responses=True)
        self._client = client

    def _key(self, session_hash: str) -> str:
        return f"{self._prefix}{session_hash}"

    async def create(self, token: UpstreamToken, principal: Principal) -> tuple[str, SessionRecord]:
        session_id, record = self.new_record(token, principal)
        await self._save(record, datetime.now(timezone.utc))
        return session_id, record

    async def get(self, session_id: str) -> SessionRecord | None:
        session_hash = self.session_hash(session_id)
        raw = await self._client.get(self._key(session_hash))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode()
        record = SessionRecord.from_payload(json.loads(raw))
        now = datetime.now(timezone.utc)
        if now >= record.expires_at:
            await self.delete(session_id)
            return None
        record.last_seen_at = now
        await self._save(record, now)
        return record

    async def update_principal(self, record: SessionRecord) -> None:
        await self._save(record, datetime.now(timezone.utc))

    async def delete(self, session_id: str) -> None:
        await self._client.delete(self._key(self.session_hash(session_id)))

    async def close(self) -> None:
        close = getattr(self._client, "aclose", None) or getattr(self._client, "close", None)
        if close:
            result = close()
            if hasattr(result, "__await__"):
                await result

    async def _save(self, record: SessionRecord, now: datetime) -> None:
        ttl = self.remaining_ttl_seconds(record, now)
        await self._client.set(
            self._key(record.session_id_hash),
            json.dumps(record.to_payload(), ensure_ascii=False, separators=(",", ":")),
            ex=ttl,
        )