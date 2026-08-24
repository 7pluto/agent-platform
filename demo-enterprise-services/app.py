"""Deterministic protocol-real upstreams for Agent Platform acceptance tests.

The service emulates public HTTP contracts only. It never replaces the actual
provider acceptance gate and is intentionally reachable only on the Compose
network.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
from typing import Any
from urllib.parse import parse_qs, urlsplit


API_KEY = "demo-provider-key"


def _last_message(payload: dict[str, Any], role: str) -> dict[str, Any] | None:
    messages = payload.get("messages", [])
    if not isinstance(messages, list):
        return None
    for item in reversed(messages):
        if isinstance(item, dict) and item.get("role") == role:
            return item
    return None


def _model_response(payload: dict[str, Any]) -> dict[str, Any]:
    tool_message = _last_message(payload, "tool")
    if tool_message is not None:
        observation = str(tool_message.get("content", ""))
        return {"choices": [{"message": {"role": "assistant", "content": f"已完成业务查询。依据：{observation[:500]}"}}]}

    user_message = _last_message(payload, "user") or {}
    question = str(user_message.get("content", ""))
    if "项目代号是什么" in question:
        previous_user_messages = [
            str(item.get("content", ""))
            for item in payload.get("messages", [])[:-1]
            if isinstance(item, dict) and item.get("role") == "user"
        ]
        if any("项目代号是星河" in content for content in previous_user_messages):
            return {"choices": [{"message": {"role": "assistant", "content": "当前会话中的项目代号是星河。"}}]}
    tools = payload.get("tools", []) if isinstance(payload.get("tools"), list) else []
    tool_specs = [
        (
            str(item.get("function", {}).get("name", "")),
            str(item.get("function", {}).get("description", "")),
        )
        for item in tools
        if isinstance(item, dict) and isinstance(item.get("function"), dict)
    ]
    knowledge_tools = [name for name, _ in tool_specs if "knowledge_search" in name.lower()]

    selected = None
    arguments: dict[str, Any] = {}
    if "本地" in question and knowledge_tools:
        selected, arguments = knowledge_tools[0], {"query": question, "top_k": 5}
    elif "RAGFlow" in question and len(knowledge_tools) >= 2:
        selected, arguments = knowledge_tools[1], {"query": question, "top_k": 5}
    elif "企业知识 API" in question and len(knowledge_tools) >= 3:
        selected, arguments = knowledge_tools[2], {"query": question, "top_k": 5}

    for name, description in tool_specs:
        if selected:
            break
        lowered = name.lower()
        if "客户" in question and ("customer" in lowered or "crm" in lowered):
            selected, arguments = name, {"customer_id": "C-1001"}
            break
        if "考勤" in question and not any(marker in question for marker in ("本地", "RAGFlow", "企业知识 API")) and "knowledge_search" in lowered:
            selected, arguments = name, {"query": question, "top_k": 5}
            break
        if "工单" in question and ("ticket" in lowered or "work_order" in lowered):
            selected, arguments = name, {"ticket_id": "T-1001"}
            break
        if any(word in question for word in ("Dify", "流程", "制度")) and "dify" in lowered:
            selected, arguments = name, {"query": question}
            break

    if selected:
        return {
            "choices": [{"message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call-demo-1",
                    "type": "function",
                    "function": {"name": selected, "arguments": json.dumps(arguments, ensure_ascii=False)},
                }],
            }}],
        }
    return {"choices": [{"message": {"role": "assistant", "content": f"这是企业验收模型的直接回答：{question}"}}]}


def _embedding(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    vector = [0.0] * 1024
    for index, value in enumerate(digest):
        vector[index] = (value - 127.5) / 127.5
    return vector


def route(method: str, path: str, headers: dict[str, str], body: dict[str, Any] | None) -> tuple[int, dict[str, Any]]:
    parsed = urlsplit(path)
    payload = body or {}
    if parsed.path == "/healthz":
        return 200, {"status": "ok", "service": "demo-enterprise-services"}

    authorization = headers.get("authorization", "")
    if parsed.path.startswith(("/v1/", "/api/v1/")) and authorization != f"Bearer {API_KEY}":
        return 401, {"code": "UNAUTHORIZED", "message": "invalid demonstration credential"}

    if method == "GET" and parsed.path == "/v1/parameters":
        return 200, {
            "user_input_form": [{"text-input": {"label": "业务问题", "variable": "query", "required": True}}],
            "opening_statement": "企业制度查询流程已连接",
            "suggested_questions": ["员工考勤管理办法是什么？"],
            "file_upload": {"enabled": False},
        }
    if method == "POST" and parsed.path == "/v1/chat-messages":
        query = str(payload.get("query", ""))
        return 200, {
            "answer": f"Dify 企业制度流程回答：{query}。员工应按规定打卡，异常考勤需在两个工作日内补交说明。",
            "conversation_id": "dify-conversation-demo",
            "message_id": "dify-message-demo",
            "metadata": {
                "usage": {"total_tokens": 64},
                "retriever_resources": [{"document_name": "员工考勤管理办法.pdf", "score": 0.96}],
            },
        }
    if method == "POST" and parsed.path == "/v1/workflows/run":
        return 200, {
            "workflow_run_id": "workflow-demo-1",
            "data": {"id": "workflow-demo-1", "status": "succeeded", "outputs": {"result": "流程审批完成"}, "elapsed_time": 0.1, "total_tokens": 40},
        }
    if method == "GET" and parsed.path == "/api/v1/datasets":
        return 200, {"code": 0, "data": [
            {"id": "dataset-hr-policy", "name": "人事制度库", "description": "考勤、休假与入离职制度"},
            {"id": "dataset-finance-policy", "name": "财务制度库", "description": "报销与预算制度"},
            {"id": "dataset-customer-service", "name": "客服知识库", "description": "工单与服务规范"},
        ]}
    if method == "POST" and parsed.path == "/api/v1/retrieval":
        dataset_ids = payload.get("dataset_ids", [])
        dataset_id = str(dataset_ids[0]) if isinstance(dataset_ids, list) and dataset_ids else "unknown"
        question = str(payload.get("question", ""))
        return 200, {"code": 0, "data": [{
            "id": f"chunk-{dataset_id}",
            "content": f"来自 {dataset_id} 的检索结果：{question}。异常考勤应在两个工作日内补交说明。",
            "similarity": 0.94,
            "document_id": "document-policy-1",
            "document_name": "企业管理制度.pdf",
        }]}
    if method == "POST" and parsed.path == "/knowledge/search":
        query = str(payload.get("query", ""))
        knowledge_id = str(payload.get("knowledge_id", "enterprise-hr"))
        return 200, {"data": {"items": [{
            "id": "remote-hit-1",
            "text": f"企业知识 API（{knowledge_id}）命中：{query}",
            "title": "员工制度摘要",
            "score": 0.93,
            "metadata": {"department": "人力资源部", "classification": "internal"},
        }]}}
    if method in {"GET", "POST"} and parsed.path == "/tickets/query":
        query = parse_qs(parsed.query)
        ticket_id = str(payload.get("ticket_id") or (query.get("ticket_id") or ["T-1001"])[0])
        return 200, {"ticket": {"id": ticket_id, "status": "处理中", "owner": "客服一组", "summary": "客户网络接入异常"}}
    if method == "POST" and parsed.path == "/v1/chat/completions":
        return 200, _model_response(payload)
    if method == "POST" and parsed.path == "/v1/embeddings":
        values = payload.get("input", [])
        texts = values if isinstance(values, list) else [str(values)]
        return 200, {"object": "list", "data": [{"index": index, "embedding": _embedding(str(value))} for index, value in enumerate(texts)]}
    return 404, {"code": "NOT_FOUND", "message": "unknown demonstration endpoint"}


class Handler(BaseHTTPRequestHandler):
    def _handle(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw) if raw else None
        except ValueError:
            body = None
        status, payload = route(self.command, self.path, {key.lower(): value for key, value in self.headers.items()}, body)
        response = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    do_GET = _handle
    do_POST = _handle

    def log_message(self, *_: Any) -> None:
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8091), Handler).serve_forever()
