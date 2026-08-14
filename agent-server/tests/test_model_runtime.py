import asyncio
import os

import httpx

from app.core.errors import ApiError
from app.core.secrets import resolve_env_secret
from app.iam.models import Principal
from app.resources.models import ModelDefinitionCreate, ModelVersionCreate, ResourceVersionStatus
from app.resources.openai_compatible import OpenAICompatibleModel
from app.resources.store import ResourceStore
from app.runtime.adapter import OpenAICompatibleRuntimeAdapter


def _principal() -> Principal:
    return Principal(provider="mock", external_user_id="user", external_org_id="org", tenant_id="tenant", display_name="User")


def test_model_requires_successful_connection_before_publish() -> None:
    async def run() -> None:
        store = ResourceStore()
        model = await store.create_model(ModelDefinitionCreate(slug="qwen-test", display_name="Qwen Test", config={"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-plus", "secret_ref": "vault://12345678-1234-1234-1234-123456789abc"}), _principal())
        version = await store.create_model_version(model.model_id, ModelVersionCreate(), _principal())
        try:
            await store.publish_model_version(version.model_version_id, _principal())
        except ApiError as exc:
            assert exc.code == "MODEL_CONNECTION_REQUIRED"
        else:
            raise AssertionError("unverified model version was published")
        await store.record_connection_test(version.model_version_id, _principal(), True, "ok")
        assert (await store.publish_model_version(version.model_version_id, _principal())).status == ResourceVersionStatus.PUBLISHED
    asyncio.run(run())


def test_env_secret_reference_is_strict(monkeypatch) -> None:
    monkeypatch.setenv("QWEN_API_KEY", "test-secret")
    assert resolve_env_secret("env://QWEN_API_KEY") == "test-secret"
    for value in ("secret://qwen", "env://qwen_api_key"):
        try:
            resolve_env_secret(value)
        except ApiError as exc:
            assert exc.code == "INVALID_SECRET_REF"
        else:
            raise AssertionError("invalid secret ref accepted")


def test_openai_compatible_call_has_no_secret_in_body(monkeypatch) -> None:
    monkeypatch.setenv("QWEN_API_KEY", "test-secret")

    async def run() -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["Authorization"] == "Bearer test-secret"
            assert b"test-secret" not in request.content
            return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})
        model = OpenAICompatibleModel.from_config({"base_url": "https://model.example/v1", "model": "qwen-plus", "secret_ref": "env://QWEN_API_KEY"})
        transport = httpx.MockTransport(handler)
        original = httpx.AsyncClient
        class Client(original):
            def __init__(self, *args, **kwargs):
                kwargs["transport"] = transport
                super().__init__(*args, **kwargs)
        monkeypatch.setattr(httpx, "AsyncClient", Client)
        assert await model.complete(system_prompt="test", message="hello") == "OK"
    asyncio.run(run())


def test_denied_optional_tool_returns_observation_and_does_not_abort_run() -> None:
    async def run() -> None:
        events: list[tuple[str, dict]] = []

        async def emit(event: str, data: dict) -> None:
            events.append((event, data))

        result = await OpenAICompatibleRuntimeAdapter._denied_tool_result(
            "knowledge_search_restricted",
            {"resource_type": "KNOWLEDGE", "resource_version_id": "version-1"},
            emit,
        )
        assert result["error"]["code"] == "RESOURCE_FORBIDDEN"
        assert "其他已授权能力" in result["error"]["message"]
        assert events == [("tool.denied", {
            "tool": "knowledge_search_restricted",
            "code": "RESOURCE_FORBIDDEN",
            "resource_type": "KNOWLEDGE",
            "resource_version_id": "version-1",
            "message": result["error"]["message"],
        })]

    asyncio.run(run())
