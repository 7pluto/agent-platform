import asyncio

from pydantic import ValidationError

from app.config import Settings
from app.iam.models import Principal
from app.iam.providers import UpstreamToken
from app.session.redis_store import RedisSessionStore
from app.session.store import SessionStore


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expiry: dict[str, int] = {}
        self.closed = False

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, ex: int) -> None:
        self.values[key] = value
        self.expiry[key] = ex

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)
        self.expiry.pop(key, None)

    async def aclose(self) -> None:
        self.closed = True


def _principal() -> Principal:
    return Principal(
        provider="mock",
        external_user_id="user-demo",
        external_org_id="org-demo",
        tenant_id="tenant-demo",
        display_name="Demo User",
    )


def test_memory_session_store_uses_async_contract() -> None:
    async def run() -> None:
        store = SessionStore(Settings(app_env="test"))
        session_id, record = await store.create(UpstreamToken("token"), _principal())
        assert await store.upstream_token(record) == UpstreamToken("token")
        assert await store.get(session_id) is not None
        await store.delete(session_id)
        assert await store.get(session_id) is None

    asyncio.run(run())


def test_redis_session_store_encrypts_token_and_slides_ttl() -> None:
    async def run() -> None:
        fake = FakeRedis()
        store = RedisSessionStore(Settings(app_env="test", session_storage_mode="redis"), client=fake)
        session_id, record = await store.create(UpstreamToken("upstream-secret"), _principal())
        key = store._key(record.session_id_hash)
        assert "upstream-secret" not in fake.values[key]
        loaded = await store.get(session_id)
        assert loaded is not None
        assert await store.upstream_token(loaded) == UpstreamToken("upstream-secret")
        loaded.principal = loaded.principal.model_copy(update={"display_name": "Refreshed"})
        await store.update_principal(loaded)
        assert (await store.get(session_id)).principal.display_name == "Refreshed"
        assert fake.expiry[key] <= store.idle_seconds
        await store.delete(session_id)
        assert await store.get(session_id) is None
        await store.close()
        assert fake.closed

    asyncio.run(run())


def test_prod_requires_redis_session_storage() -> None:
    try:
        Settings(app_env="prod", iam_mode="ruoyi", storage_mode="postgres", session_storage_mode="memory")
    except ValidationError as exc:
        assert "AGENT_SESSION_STORAGE_MODE=redis" in str(exc)
    else:
        raise AssertionError("production accepted memory session storage")