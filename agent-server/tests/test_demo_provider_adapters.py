from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
from typing import Any

import httpx

from app.iam.models import Principal
from app.knowledge.providers.ragflow import RagflowKnowledgeProvider
from app.knowledge.providers.remote_http import RemoteHttpKnowledgeProvider
from app.mcp.service import McpClient
from app.runtime.dify_flow import DifyFlowClient


def _load(relative: str, name: str):
    path = Path(__file__).parents[2] / relative / "app.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


enterprise = _load("demo-enterprise-services", "demo_enterprise_adapters")
crm = _load("demo-crm-mcp", "demo_crm_adapters")


class DemoSafeHttp:
    async def request(self, method: str, url: str, *, headers: dict[str, str] | None = None, json_body: Any = None, **_: Any) -> httpx.Response:
        target = httpx.URL(url)
        path = target.raw_path.decode("ascii")
        if target.query:
            path = f"{path}?{target.query.decode('ascii')}"
        lowered_headers = {key.lower(): value for key, value in (headers or {}).items()}
        if target.host == "demo-crm-mcp":
            status, result = crm.route(json_body or {})
            envelope = {"jsonrpc": "2.0", "id": "agent-platform"}
            envelope["result" if status == 200 else "error"] = result if status == 200 else result["error"]
            return httpx.Response(status, json=envelope, request=httpx.Request(method, url))
        status, result = enterprise.route(method, path, lowered_headers, json_body)
        return httpx.Response(status, json=result, request=httpx.Request(method, url))


def _principal() -> Principal:
    return Principal(provider="mock", external_user_id="business-user", external_org_id="org-demo", tenant_id="tenant-demo", display_name="业务用户")


def test_dify_adapter_runs_real_demo_protocol(monkeypatch) -> None:
    monkeypatch.setattr("app.runtime.dify_flow.safe_http_client", DemoSafeHttp())

    async def scenario() -> None:
        client = DifyFlowClient("http://demo-enterprise-services:8091/v1", "demo-provider-key", "CHATFLOW", 10, ("demo-enterprise-services",))
        inspection = await client.inspect_application()
        result = await client.invoke({"query": "员工考勤管理办法"}, user_id="business-user")
        assert inspection["input_form"][0]["text-input"]["variable"] == "query"
        assert "两个工作日" in result["answer"]
        assert result["retriever_resources"][0]["document_name"] == "员工考勤管理办法.pdf"

    asyncio.run(scenario())


def test_ragflow_and_remote_knowledge_adapters_run_real_demo_protocol(monkeypatch) -> None:
    demo_http = DemoSafeHttp()
    monkeypatch.setattr("app.knowledge.providers.ragflow.safe_http_client", demo_http)
    monkeypatch.setattr("app.knowledge.providers.remote_http.safe_http_client", demo_http)

    async def no_auth(*_: Any, **__: Any) -> dict[str, str]:
        return {"Authorization": "Bearer demo-provider-key"}

    monkeypatch.setattr("app.knowledge.providers.ragflow.mcp_auth_headers", no_auth)
    monkeypatch.setattr("app.knowledge.providers.remote_http.mcp_auth_headers", no_auth)

    async def scenario() -> None:
        ragflow = RagflowKnowledgeProvider(_principal())
        datasets = await ragflow.discover_datasets({
            "endpoint": "http://demo-enterprise-services:8091",
            "egress_allowlist": ["demo-enterprise-services"],
        })
        assert len(datasets) == 3
        rag_result = await ragflow.search(
            knowledge_version_id="ragflow-knowledge-v1",
            config={
                "endpoint": "http://demo-enterprise-services:8091",
                "egress_allowlist": ["demo-enterprise-services"],
                "external_dataset_id": "dataset-hr-policy",
            },
            query="考勤异常怎么处理", top_k=5,
        )
        assert rag_result.hits[0].metadata["dataset_id"] == "dataset-hr-policy"

        remote = RemoteHttpKnowledgeProvider(_principal())
        remote_result = await remote.search(
            knowledge_version_id="remote-knowledge-v1",
            config={
                "endpoint": "http://demo-enterprise-services:8091",
                "search_path": "/knowledge/search",
                "method": "POST",
                "egress_allowlist": ["demo-enterprise-services"],
                "request_mapping": {"query_field": "query", "top_k_field": "top_k", "static_body": {"knowledge_id": "hr"}},
                "response_mapping": {"items_path": "data.items", "content_field": "text", "id_field": "id", "title_field": "title", "score_field": "score", "metadata_field": "metadata"},
            },
            query="员工请假", top_k=3,
        )
        assert remote_result.hits[0].title == "员工制度摘要"
        assert remote_result.hits[0].metadata["department"] == "人力资源部"

    asyncio.run(scenario())


def test_mcp_adapter_discovers_and_invokes_independently_governable_tools(monkeypatch) -> None:
    monkeypatch.setattr("app.mcp.service.safe_http_client", DemoSafeHttp())

    async def scenario() -> None:
        client = McpClient()
        tools = await client.discover(
            "http://demo-crm-mcp:8090/mcp", egress_allowlist=["demo-crm-mcp"],
        )
        assert [tool["name"] for tool in tools] == ["query_customer", "list_customer_orders"]
        customer = await client.invoke(
            "http://demo-crm-mcp:8090/mcp", "query_customer", {"customer_id": "C-1001"},
            egress_allowlist=["demo-crm-mcp"],
        )
        orders = await client.invoke(
            "http://demo-crm-mcp:8090/mcp", "list_customer_orders", {"customer_id": "C-1001", "limit": 2},
            egress_allowlist=["demo-crm-mcp"],
        )
        assert "示例客户" in customer["content"][0]["text"]
        assert len(json.loads(orders["content"][0]["text"])["orders"]) == 2

    asyncio.run(scenario())
