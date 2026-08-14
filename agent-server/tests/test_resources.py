import asyncio

from app.core.errors import ApiError
from app.iam.models import Principal
from app.resources.models import ModelDefinitionCreate, ModelVersionCreate, ResourceVersionStatus
from app.resources.store import ResourceStore


def test_model_versions_publish_and_reject_plaintext_secrets() -> None:
    async def run() -> None:
        store = ResourceStore()
        principal = Principal(provider="mock", external_user_id="user", external_org_id="org", tenant_id="tenant", display_name="User")
        try:
            await store.create_model(ModelDefinitionCreate(slug="secret-model", display_name="Secret", provider="openai-compatible", config={"base_url": "https://model.example/v1", "model": "qwen-test", "api_key": "plain"}), principal)
        except ApiError as exc:
            assert exc.code == "SECRET_VALUE_FORBIDDEN"
        else:
            raise AssertionError("plaintext model secret was accepted")
        model = await store.create_model(ModelDefinitionCreate(slug="safe-model", display_name="Safe", provider="openai-compatible", config={"base_url": "https://model.example/v1", "model": "qwen-test", "secret_ref": "vault://12345678-1234-1234-1234-123456789abc"}), principal)
        version = await store.create_model_version(model.model_id, ModelVersionCreate(), principal)
        assert version.status == ResourceVersionStatus.DRAFT
        await store.record_connection_test(version.model_version_id, principal, True, "ok")
        assert (await store.publish_model_version(version.model_version_id, principal)).status == ResourceVersionStatus.PUBLISHED

    asyncio.run(run())
