import asyncio

import httpx

from app.core.errors import ApiError
from app.runtime.dify_flow import DifyFlowClient


def test_chatflow_maps_query_and_retrieval_metadata(monkeypatch) -> None:
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["authorization"] = request.headers.get("Authorization")
        captured["body"] = __import__("json").loads(request.content)
        return httpx.Response(
            200,
            json={
                "answer": "交付口令是 DELIVERY-PANDA-15",
                "conversation_id": "conversation-1",
                "message_id": "message-1",
                "metadata": {"retriever_resources": [{"document_name": "交付规则.pdf", "score": 0.98}]},
            },
        )

    original = httpx.AsyncClient

    def client(*args, **kwargs):
        return original(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    result = asyncio.run(DifyFlowClient("http://dify-gateway/v1", "app-secret", "CHATFLOW", 10).invoke({"query": "口令是什么"}, user_id="tenant:user"))
    assert result["answer"].endswith("DELIVERY-PANDA-15")
    assert result["retriever_resources"][0]["score"] == 0.98
    assert captured["path"] == "/v1/chat-messages"
    assert captured["authorization"] == "Bearer app-secret"
    assert captured["body"]["user"] == "tenant:user"


def test_chatflow_rejects_missing_query() -> None:
    try:
        asyncio.run(DifyFlowClient("http://dify-gateway/v1", "app-secret", "CHATFLOW", 10).invoke({}, user_id="u"))
    except ApiError as exc:
        assert exc.code == "DIFY_FLOW_QUERY_REQUIRED"
    else:
        raise AssertionError("missing Chatflow query was accepted")


def test_inspection_returns_dify_input_contract(monkeypatch) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/parameters"
        assert request.headers.get("Authorization") == "Bearer app-secret"
        return httpx.Response(200, json={
            "user_input_form": [
                {"text-input": {"label": "Project code", "variable": "project_code", "required": True}},
                {"select": {"label": "Language", "variable": "language", "required": False, "options": ["zh", "en"]}},
            ],
            "opening_statement": "How can I help?",
            "suggested_questions": ["Show project status"],
        })

    original = httpx.AsyncClient

    def client(*args, **kwargs):
        return original(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    result = asyncio.run(DifyFlowClient("http://dify-gateway/v1", "app-secret", "WORKFLOW", 10).inspect_application())
    assert result["available"] is True
    assert result["input_form"][0]["text-input"]["variable"] == "project_code"
    assert result["suggested_questions"] == ["Show project status"]
