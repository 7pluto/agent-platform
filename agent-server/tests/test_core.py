import asyncio
from uuid import uuid4

from app.iam.mock import MockIamProvider
from app.iam.providers import IamAuthError, UpstreamToken
from app.iam.models import Principal
from app.runtime.models import RunCreateRequest, RunStatus
from app.runtime.store import RunStore


def test_mock_iam_contract() -> None:
    async def run() -> None:
        provider = MockIamProvider()
        token = await provider.exchange_ticket("dev-ticket")
        identity = await provider.resolve_identity(token)
        assert identity.external_user_id == "user-demo"
        assert identity.external_org_id == "org-demo"
        assert "agent_admin" in identity.role_codes

        try:
            await provider.resolve_identity(UpstreamToken("bad"))
        except IamAuthError:
            pass
        else:
            raise AssertionError("invalid mock token was accepted")

    asyncio.run(run())


def test_one_running_run_per_thread_and_pending_queue() -> None:
    async def run() -> None:
        store = RunStore()
        principal = Principal(
            provider="mock",
            external_user_id="user-demo",
            external_org_id="org-demo",
            tenant_id="tenant-demo",
            display_name="Demo User",
        )
        thread_id = uuid4()
        deployment_id = uuid4()
        first = await store.create(RunCreateRequest(deployment_id=deployment_id, thread_id=thread_id, message="one"), principal, "one")
        second = await store.create(RunCreateRequest(deployment_id=deployment_id, thread_id=thread_id, message="two"), principal, "two")
        assert first.status == RunStatus.RUNNING
        assert first.execution_manifest is not None
        assert first.execution_manifest.manifest_hash
        assert second.status == RunStatus.PENDING
        await store.finish(first.run_id)
        assert (await store.get(second.run_id, principal)).status == RunStatus.RUNNING

    asyncio.run(run())

def test_same_thread_id_is_independent_between_tenants() -> None:
    async def run() -> None:
        store = RunStore()
        thread_id = uuid4()
        deployment_id = uuid4()
        tenant_a = Principal(
            provider="mock",
            external_user_id="user-a",
            external_org_id="org-a",
            tenant_id="tenant-a",
            display_name="User A",
        )
        tenant_b = Principal(
            provider="mock",
            external_user_id="user-b",
            external_org_id="org-b",
            tenant_id="tenant-b",
            display_name="User B",
        )
        run_a = await store.create(
            RunCreateRequest(deployment_id=deployment_id, thread_id=thread_id, message="tenant a"), tenant_a, "a"
        )
        run_b = await store.create(
            RunCreateRequest(deployment_id=deployment_id, thread_id=thread_id, message="tenant b"), tenant_b, "b"
        )
        assert run_a.status == RunStatus.RUNNING
        assert run_b.status == RunStatus.RUNNING

    asyncio.run(run())