from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_demo_module():
    path = Path(__file__).parents[2] / "demo-enterprise-services" / "app.py"
    spec = importlib.util.spec_from_file_location("demo_enterprise_services", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


demo = _load_demo_module()
AUTH = {"authorization": "Bearer demo-provider-key"}


def test_demo_dify_contract_supports_discovery_chatflow_and_retrieval_evidence() -> None:
    status, parameters = demo.route("GET", "/v1/parameters", AUTH, None)
    assert status == 200
    assert parameters["user_input_form"][0]["text-input"]["variable"] == "query"

    status, answer = demo.route("POST", "/v1/chat-messages", AUTH, {"query": "员工考勤管理办法"})
    assert status == 200
    assert "员工考勤管理办法" in answer["answer"]
    assert answer["metadata"]["retriever_resources"][0]["score"] == 0.96


def test_demo_ragflow_contract_exposes_three_datasets_and_fixed_dataset_retrieval() -> None:
    status, datasets = demo.route("GET", "/api/v1/datasets", AUTH, None)
    assert status == 200
    assert [item["id"] for item in datasets["data"]] == [
        "dataset-hr-policy", "dataset-finance-policy", "dataset-customer-service",
    ]

    status, result = demo.route("POST", "/api/v1/retrieval", AUTH, {
        "question": "考勤异常怎么处理", "dataset_ids": ["dataset-hr-policy"], "top_k": 5,
    })
    assert status == 200
    assert result["data"][0]["document_name"] == "企业管理制度.pdf"
    assert "两个工作日" in result["data"][0]["content"]


def test_demo_remote_knowledge_and_ticket_contracts_are_business_readable() -> None:
    status, knowledge = demo.route("POST", "/knowledge/search", {}, {"knowledge_id": "hr", "query": "请假"})
    assert status == 200
    assert knowledge["data"]["items"][0]["metadata"]["department"] == "人力资源部"

    status, ticket = demo.route("POST", "/tickets/query", {}, {"ticket_id": "T-1008"})
    assert status == 200
    assert ticket["ticket"]["id"] == "T-1008"
    assert ticket["ticket"]["status"] == "处理中"


def test_demo_model_autonomously_selects_matching_registered_capability() -> None:
    status, response = demo.route("POST", "/v1/chat/completions", AUTH, {
        "messages": [{"role": "user", "content": "查询客户信息"}],
        "tools": [{"type": "function", "function": {"name": "query_customer", "parameters": {"type": "object"}}}],
    })
    assert status == 200
    call = response["choices"][0]["message"]["tool_calls"][0]
    assert call["function"]["name"] == "query_customer"
    assert "C-1001" in call["function"]["arguments"]


@pytest.mark.parametrize(
    ("question", "expected_name"),
    [
        ("查询本地员工考勤管理办法", "knowledge_search_local001"),
        ("使用 RAGFlow 查询考勤异常处理", "knowledge_search_ragflow1"),
        ("使用企业知识 API 查询员工请假", "knowledge_search_remote01"),
    ],
)
def test_demo_model_uses_knowledge_business_description_to_select_provider(question: str, expected_name: str) -> None:
    status, response = demo.route("POST", "/v1/chat/completions", AUTH, {
        "messages": [{"role": "user", "content": question}],
        "tools": [
            {"type": "function", "function": {"name": "knowledge_search_local001", "description": "Search the knowledge base ‘验收·本地员工手册’.", "parameters": {"type": "object"}}},
            {"type": "function", "function": {"name": "knowledge_search_ragflow1", "description": "Search the knowledge base ‘验收·RAGFlow 人事制度库’.", "parameters": {"type": "object"}}},
            {"type": "function", "function": {"name": "knowledge_search_remote01", "description": "Search the knowledge base ‘验收·企业知识 API’.", "parameters": {"type": "object"}}},
        ],
    })
    assert status == 200
    call = response["choices"][0]["message"]["tool_calls"][0]
    assert call["function"]["name"] == expected_name


def test_demo_model_returns_a_final_answer_after_tool_observation_and_embeddings_are_1024d() -> None:
    status, response = demo.route("POST", "/v1/chat/completions", AUTH, {
        "messages": [{"role": "tool", "content": "客户为示例客户"}],
    })
    assert status == 200
    assert response["choices"][0]["message"]["content"].startswith("已完成业务查询")

    status, embeddings = demo.route("POST", "/v1/embeddings", AUTH, {"input": ["员工考勤"]})
    assert status == 200
    assert len(embeddings["data"][0]["embedding"]) == 1024


def test_demo_provider_rejects_invalid_credential_without_echoing_it() -> None:
    status, response = demo.route("GET", "/api/v1/datasets", {"authorization": "Bearer wrong-secret"}, None)
    assert status == 401
    assert "wrong-secret" not in str(response)


def test_demo_model_answers_from_current_conversation_history_only() -> None:
    status, response = demo.route("POST", "/v1/chat/completions", AUTH, {
        "messages": [
            {"role": "user", "content": "项目代号是星河"},
            {"role": "assistant", "content": "我已记住当前会话的项目代号。"},
            {"role": "user", "content": "项目代号是什么？"},
        ],
    })
    assert status == 200
    assert response["choices"][0]["message"]["content"] == "当前会话中的项目代号是星河。"

    _, isolated = demo.route("POST", "/v1/chat/completions", AUTH, {
        "messages": [{"role": "user", "content": "项目代号是什么？"}],
    })
    assert "星河" not in isolated["choices"][0]["message"]["content"]
