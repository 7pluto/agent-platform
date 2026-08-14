import asyncio

import httpx
import pytest

from app.core.errors import ApiError
from app.iam.models import Principal
from app.resources.registry_models import ResourceDefinitionCreate, ResourceType
from app.resources.registry_store import ResourceRegistryStore
from app.runtime.http_tool import http_tool_client, render_template


def test_http_tool_template_requires_declared_argument() -> None:
    assert render_template({"keyword": "{{ query }}"}, {"query": "leave policy"}) == {"keyword": "leave policy"}
    with pytest.raises(ApiError, match="HTTP_TOOL_ARGUMENT_MISSING"):
        render_template("{{ employee_id }}", {})


def test_http_tool_registry_rejects_uncontrolled_path() -> None:
    principal = Principal(provider="test", external_user_id="admin", external_org_id="org", tenant_id="tenant", display_name="Admin")

    async def run() -> None:
        store = ResourceRegistryStore()
        with pytest.raises(ApiError, match="INVALID_HTTP_TOOL_CONFIG"):
            await store.create_definition(ResourceDefinitionCreate(
                resource_type=ResourceType.TOOL,
                slug="unsafe-http-tool",
                display_name="Unsafe HTTP Tool",
                draft_config={
                    "kind": "HTTP", "tool_name": "unsafe_http", "endpoint": "https://api.example.com",
                    "path": "/v1/../admin", "egress_allowlist": ["api.example.com"],
                },
            ), principal)

    asyncio.run(run())


def test_http_tool_invokes_fixed_target_with_rendered_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run() -> None:
        captured: dict = {}

        async def fake_request(method: str, url: str, **kwargs: object) -> httpx.Response:
            captured.update({"method": method, "url": url, **kwargs})
            return httpx.Response(200, json={"items": ["A"]}, request=httpx.Request(method, url))

        monkeypatch.setattr("app.runtime.http_tool.safe_http_client.request", fake_request)
        output = await http_tool_client.invoke(
            {
                "kind": "HTTP", "tool_name": "search_policy", "endpoint": "https://api.example.com/base",
                "path": "/search", "method": "GET", "egress_allowlist": ["api.example.com"],
                "query_template": {"q": "{{query}}"},
            },
            {"query": "leave policy"}, "tenant", "user",
        )
        assert captured["method"] == "GET"
        assert captured["url"] == "https://api.example.com/base/search?q=leave+policy"
        assert output == {"status_code": 200, "body": {"items": ["A"]}}

    asyncio.run(run())
