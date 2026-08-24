#!/usr/bin/env python3
"""Provision and exercise the complete internal business acceptance stack.

Run this after the Compose stack is healthy. The script uses only public Agent
Platform APIs, creates uniquely named immutable resources, publishes one Agent,
executes four autonomous capability scenarios, and prints a secret-safe report.
"""

from __future__ import annotations

import argparse
import http.cookiejar
import io
import json
import time
import urllib.error
import urllib.request
import uuid
import zipfile


DEMO_KEY = "demo-provider-key"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    cookies = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
    csrf = ""

    def request(path: str, method: str = "GET", payload: dict | None = None, *, idempotency_key: str | None = None):
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if csrf and method != "GET":
            headers["X-CSRF-Token"] = csrf
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        req = urllib.request.Request(args.base_url + path, data=body, headers=headers, method=method)
        try:
            with opener.open(req, timeout=45) as response:
                return json.load(response) if response.status != 204 else None
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {path} failed with HTTP {exc.code}: {detail}") from exc

    def upload_knowledge(version_id: str, filename: str, content_type: str, content: bytes):
        boundary = f"----agent-platform-{uuid.uuid4().hex}"
        body = bytearray()
        for name, value in (("knowledge_resource_version_id", version_id),):
            body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
        body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\nContent-Type: {content_type}\r\n\r\n".encode())
        body.extend(content)
        body.extend(f"\r\n--{boundary}--\r\n".encode())
        req = urllib.request.Request(
            args.base_url + "/knowledge/documents/upload", data=bytes(body), method="POST",
            headers={"Accept": "application/json", "Content-Type": f"multipart/form-data; boundary={boundary}", "X-CSRF-Token": csrf},
        )
        try:
            with opener.open(req, timeout=45) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"knowledge upload failed with HTTP {exc.code}: {detail}") from exc

    def docx_bytes(text: str) -> bytes:
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
            archive.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
            archive.writestr("word/document.xml", f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p><w:sectPr/></w:body></w:document>')
        return output.getvalue()

    def pdf_bytes(text: str) -> bytes:
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("latin-1")
        objects = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        ]
        output = bytearray(b"%PDF-1.4\n")
        offsets = [0]
        for index, value in enumerate(objects, 1):
            offsets.append(len(output)); output.extend(f"{index} 0 obj\n".encode()); output.extend(value); output.extend(b"\nendobj\n")
        xref = len(output); output.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
        for offset in offsets[1:]: output.extend(f"{offset:010d} 00000 n \n".encode())
        output.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
        return bytes(output)

    login = request("/auth/exchange", "POST", {"ticket_code": "dev-ticket"})
    csrf = login["csrf_token"]
    owner_id = login["principal"]["external_user_id"]
    suffix = f"{int(time.time())}-{uuid.uuid4().hex[:6]}"

    def product_fields(summary: str, when: str, input_summary: str, output_summary: str, tags: list[str]) -> dict:
        return {
            "owner_user_id": owner_id,
            "one_line_summary": summary,
            "when_to_use": when,
            "input_summary": input_summary,
            "output_summary": output_summary,
            "risk_level": "LOW",
            "read_only": True,
            "tags": tags,
            "publication_scope": "PERSONAL",
            "publication_subjects": [],
        }

    def grant(resource_type: str, resource_version_id: str) -> None:
        request("/resource-grants", "POST", {
            "subject_type": "USER", "subject_id": owner_id,
            "resource_type": resource_type, "resource_id": resource_version_id,
            "actions": ["VIEW", "USE", "EDIT", "PUBLISH", "MANAGE"], "effect": "ALLOW",
        })

    def generic_resource(resource_type: str, name: str, config: dict) -> tuple[str, str]:
        slug = f"accept-{name}-{suffix}".lower()[:63]
        definition = request("/resources", "POST", {
            "resource_type": resource_type, "slug": slug,
            "display_name": f"验收·{name}", "description": "自动化业务验收资源", "draft_config": config,
        })
        version = request(f"/resources/{definition['resource_id']}/versions", "POST", {"config": config})
        published = request(f"/resource-versions/{version['resource_version_id']}/publish", "POST")
        grant(resource_type, published["resource_version_id"])
        return published["resource_id"], published["resource_version_id"]

    model = request("/models/with-secret", "POST", {
        "slug": f"accept-model-{suffix}"[:63], "display_name": "验收·企业 Tool Calling 模型",
        "base_url": "http://demo-enterprise-services:8091/v1", "model": "demo-qwen-compatible",
        "api_key": DEMO_KEY, "model_mode": "CHAT",
    })
    grant("MODEL", model["model_version_id"])
    embedding_model = request("/models/with-secret", "POST", {
        "slug": f"accept-embedding-{suffix}"[:63], "display_name": "验收·企业 Embedding 模型",
        "base_url": "http://demo-enterprise-services:8091/v1", "model": "demo-embedding-1024",
        "api_key": DEMO_KEY, "model_mode": "EMBEDDING",
    })
    grant("MODEL", embedding_model["model_version_id"])

    _, prompt_version_id = generic_resource("PROMPT", "prompt", {
        "template": "你是企业综合助手。根据用户问题自主选择最合适的已授权能力；工具返回后必须给出简体中文最终回答。",
    })
    _, memory_version_id = generic_resource("MEMORY_POLICY", "memory", {
        "write_mode": "EXPLICIT", "read_enabled": True, "write_enabled": True,
        "ttl_days": 365, "max_items": 100, "allowed_categories": ["preference", "business"],
    })

    dify = request("/dify-applications", "POST", {
        "slug": f"accept-dify-{suffix}"[:63], "display_name": "验收·Dify 企业制度流程",
        "description": "查询员工制度并保留 Dify RAG 引用", "flow_type": "CHATFLOW",
        "base_url": "http://demo-enterprise-services:8091/v1", "api_key": DEMO_KEY,
        "tool_name": "dify_enterprise_flow", "timeout_seconds": 30, "test_query": "员工考勤管理办法",
        "owner_user_id": owner_id, "one_line_summary": "调用 Dify 企业制度流程",
        "when_to_use": "用户明确要求使用 Dify 流程或查询制度时",
        "when_not_to_use": "客户和工单查询不使用", "input_summary": "自然语言问题",
        "output_summary": "Dify 回答和检索引用", "risk_level": "LOW", "read_only": True,
        "tags": ["Dify", "制度"], "business_line": "人力资源", "audience": "全体员工",
        "usage_scenarios": "企业制度问答", "developer_user_ids": [],
        "suggested_questions": ["员工考勤管理办法是什么？"], "publication_scope": "PERSONAL",
        "publication_subjects": [],
    })
    dify_version_id = dify["resource_version"]["resource_version_id"]

    mcp_connection = request("/mcp-connections", "POST", {
        "slug": f"accept-mcp-{suffix}"[:63], "display_name": "验收·CRM MCP",
        "endpoint": "http://demo-crm-mcp:8090/mcp", "timeout_seconds": 10,
        "api_key": None, "auth_header": "Authorization", "auth_scheme": "Bearer",
    })
    grant("MCP_CONNECTION", mcp_connection["resource_version_id"])
    discovered_tools = request(f"/mcp-connections/{mcp_connection['resource_version_id']}/discover", "POST")
    assert {item["name"] for item in discovered_tools} == {"query_customer", "list_customer_orders"}
    mcp_tools = request("/mcp-tools/register-batch", "POST", {
        "connection_version_id": mcp_connection["resource_version_id"],
        "tools": [
            {"tool_name": "query_customer", "slug": f"accept-crm-customer-{suffix}"[:63], "display_name": "验收·查询 CRM 客户", "description": "按客户编号读取客户基础资料", **product_fields("查询 CRM 客户资料", "用户需要查询客户基础信息时", "客户编号", "客户基础资料", ["CRM", "MCP", "只读"])},
            {"tool_name": "list_customer_orders", "slug": f"accept-crm-orders-{suffix}"[:63], "display_name": "验收·查询客户订单", "description": "按客户编号读取订单列表", **product_fields("查询客户订单", "用户需要查询客户订单时", "客户编号", "客户订单列表", ["CRM", "MCP", "只读"])},
        ],
    })
    mcp_customer_version_id = next(item["resource_version_id"] for item in mcp_tools if item["config"]["tool_name"] == "query_customer")

    http_tool = request("/http-tools", "POST", {
        "slug": f"accept-ticket-{suffix}"[:63], "display_name": "验收·查询客服工单",
        "description": "按工单编号查询状态", "tool_name": "ticket_query",
        "endpoint": "http://demo-enterprise-services:8091", "path": "/tickets/query", "method": "POST",
        "input_schema": {"type": "object", "properties": {"ticket_id": {"type": "string"}}, "required": ["ticket_id"]},
        "body_template": {"ticket_id": "{{ticket_id}}"}, "timeout_seconds": 10,
        "test_arguments": {"ticket_id": "T-1001"},
        "header_template": {"X-Business-Source": "agent-platform"}, "response_mapping": {},
        **product_fields("查询客服工单状态", "用户提供工单编号并查询处理进度时", "工单编号", "工单状态与处理信息", ["工单", "HTTP", "只读"]),
    })
    http_tool_version_id = http_tool["resource_version"]["resource_version_id"]

    _, local_knowledge_version_id = generic_resource("KNOWLEDGE", "local-employee-handbook", {
        "provider": "LOCAL", "embedding_model_version_id": embedding_model["model_version_id"],
        "description": "本地 PDF 与 DOCX 员工手册",
    })
    upload_knowledge(
        local_knowledge_version_id, "employee-attendance.pdf", "application/pdf",
        pdf_bytes("Employee attendance policy: exceptions must be explained within two working days."),
    )
    upload_knowledge(
        local_knowledge_version_id, "员工考勤补充规定.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        docx_bytes("本地员工手册规定：考勤异常应在两个工作日内提交说明，直属负责人完成确认。"),
    )
    index_job = request("/knowledge/indexes/build", "POST", {"knowledge_resource_version_id": local_knowledge_version_id})
    deadline = time.monotonic() + args.timeout
    while True:
        jobs = request(f"/knowledge/ingest-jobs?knowledge_resource_version_id={local_knowledge_version_id}")
        current = next(item for item in jobs if item["job_id"] == index_job["job_id"])
        if current["status"] in {"COMPLETED", "FAILED"}: break
        if time.monotonic() > deadline: raise TimeoutError("local knowledge ingest timed out")
        time.sleep(1)
    if current["status"] != "COMPLETED": raise RuntimeError(f"local knowledge ingest failed: {current}")
    local_hits = request("/knowledge/retrieval-test", "POST", {
        "knowledge_resource_version_id": local_knowledge_version_id, "query": "本地员工考勤异常如何处理", "top_k": 3,
    })
    assert local_hits and any("考勤异常" in item["content"] for item in local_hits)

    ragflow_connection = request("/ragflow-connections", "POST", {
        "slug": f"accept-ragflow-{suffix}"[:63], "display_name": "验收·公司 RAGFlow",
        "endpoint": "http://demo-enterprise-services:8091", "api_key": DEMO_KEY, "timeout_seconds": 20,
    })
    grant("KNOWLEDGE_CONNECTION", ragflow_connection["resource_version_id"])
    datasets = request(f"/ragflow-connections/{ragflow_connection['resource_version_id']}/discover", "POST")
    assert len(datasets) == 3
    ragflow_knowledge = request("/ragflow-knowledge/register", "POST", {
        "connection_version_id": ragflow_connection["resource_version_id"], "dataset_id": "dataset-hr-policy",
        "slug": f"accept-ragflow-hr-{suffix}"[:63], "display_name": "验收·RAGFlow 人事制度库",
        "description": "固定绑定人事制度数据集",
        **product_fields("检索 RAGFlow 人事制度", "用户询问人事或考勤制度时", "制度问题", "制度知识片段", ["人事", "RAGFlow", "只读"]),
    })
    request("/knowledge/retrieval-test", "POST", {
        "knowledge_resource_version_id": ragflow_knowledge["resource_version_id"],
        "query": "考勤异常怎么处理", "top_k": 3,
    })

    remote_knowledge = request("/remote-http-knowledge", "POST", {
        "slug": f"accept-remote-knowledge-{suffix}"[:63], "display_name": "验收·企业知识 API",
        "description": "固定业务域的远程知识检索", "endpoint": "http://demo-enterprise-services:8091",
        "search_path": "/knowledge/search", "method": "POST", "timeout_seconds": 15,
        "query_field": "query", "top_k_field": "top_k", "static_body": {"knowledge_id": "enterprise-hr"},
        "items_path": "data.items", "id_field": "id", "content_field": "text", "title_field": "title",
        "score_field": "score", "metadata_field": "metadata", "test_query": "员工请假", "test_top_k": 3,
        **product_fields("检索企业知识 API", "用户询问企业制度且需要外部知识系统时", "自然语言问题", "外部知识片段", ["企业知识", "REMOTE_HTTP", "只读"]),
    })

    skill = request("/skills", "POST", {
        "slug": f"accept-skill-{suffix}"[:63], "display_name": "验收·企业业务查询技能",
        "description": "根据问题选择 CRM、工单或知识能力",
        "skill_md": "# 企业业务查询技能\n先判断业务对象，再选择一个最匹配的已授权工具；引用工具结果回答。",
        "tool_version_ids": [mcp_customer_version_id, http_tool_version_id],
        "knowledge_version_ids": [local_knowledge_version_id, ragflow_knowledge["resource_version_id"]],
        "test_cases": [
            {"input": "查询客户信息", "expected_behavior": "调用 CRM 客户查询"},
            {"input": "考勤异常怎么处理", "expected_behavior": "检索人事制度库"},
        ],
    })
    grant("SKILL", skill["resource_version_id"])

    agent = request("/agents", "POST", {
        "slug": f"accept-agent-{suffix}"[:63], "display_name": "验收·企业综合智能体",
        "description": "组合 Dify、MCP、HTTP、RAGFlow、Remote Knowledge、Skill 与 Memory", "draft_spec": {},
    })
    initial_version = request(f"/agents/{agent['agent_id']}/versions", "POST", {"specification": {}})
    request(f"/agent-versions/{initial_version['agent_version_id']}/publish", "POST")
    deployment = request("/deployments", "POST", {
        "agent_id": agent["agent_id"], "name": f"accept-prod-{suffix}"[:63], "description": "业务组合验收部署",
    })
    initial_revision = request(f"/deployments/{deployment['deployment_id']}/revisions", "POST", {
        "agent_version_id": initial_version["agent_version_id"], "overrides": {},
    })
    request(f"/deployments/{deployment['deployment_id']}/revisions/{initial_revision['deployment_revision_id']}/activate", "POST")

    specification = {
        "assembly_schema": "v2", "model_version_id": model["model_version_id"],
        "prompt_version_id": prompt_version_id, "memory_policy_version_id": memory_version_id,
        "skill_version_ids": [skill["resource_version_id"]],
        "tool_version_ids": [dify_version_id, mcp_customer_version_id, http_tool_version_id],
        "knowledge_version_ids": [local_knowledge_version_id, ragflow_knowledge["resource_version_id"], remote_knowledge["resource_version_id"]],
    }
    validation = request(f"/deployments/{deployment['deployment_id']}/configuration-draft/validate", "POST", {"specification": specification})
    if not validation["valid"]:
        raise RuntimeError(f"Agent validation failed: {validation['blocking_errors']}")
    published = request(
        f"/deployments/{deployment['deployment_id']}/publish-configuration", "POST",
        {"specification": specification, "base_revision_id": initial_revision["deployment_revision_id"], "publication_scope": "PERSONAL", "publication_subjects": []},
        idempotency_key=f"accept-publish-{suffix}",
    )
    memory_item = request("/memory-items", "POST", {
        "deployment_id": deployment["deployment_id"],
        "category": "preference",
        "content": "所有回答使用简体中文，并优先给出结论。",
    })

    def run_case(conversation: dict, question: str) -> tuple[dict, dict]:
        run = request(
            f"/deployments/{deployment['deployment_id']}/runs", "POST",
            {
                "deployment_id": deployment["deployment_id"],
                "conversation_id": conversation["conversation"]["conversation_id"],
                "thread_id": conversation["thread"]["thread_id"], "message": question,
            },
            idempotency_key=f"accept-run-{uuid.uuid4()}",
        )
        deadline = time.monotonic() + args.timeout
        while True:
            state = request(f"/runs/{run['run_id']}")
            if state["status"] in {"COMPLETED", "FAILED", "CANCELLED"}:
                break
            if time.monotonic() > deadline:
                raise TimeoutError(f"Run {run['run_id']} timed out")
            time.sleep(1)
        detail = request(f"/runs/{run['run_id']}/detail")
        if DEMO_KEY in json.dumps(detail, ensure_ascii=False):
            raise AssertionError("provider credential leaked into Run detail")
        assert state["status"] == "COMPLETED", detail
        memory_event = next(event for event in detail["events"] if event["event"] == "memory.read")
        assert memory_event["data"]["count"] == 1
        return state, detail

    cases = [
        ("查询客户信息", "query_customer", "tool.completed"),
        ("查询本地员工考勤管理办法", f"knowledge_search_{local_knowledge_version_id[:8]}", "rag.retrieved"),
        ("使用 RAGFlow 查询考勤异常处理", f"knowledge_search_{ragflow_knowledge['resource_version_id'][:8]}", "rag.retrieved"),
        ("使用企业知识 API 查询员工请假", f"knowledge_search_{remote_knowledge['resource_version_id'][:8]}", "rag.retrieved"),
        ("查询工单处理状态", "ticket_query", "tool.completed"),
        ("使用 Dify 流程查询制度", "dify_enterprise_flow", "dify.flow.completed"),
    ]
    case_results = []
    for question, expected_tool_prefix, expected_event in cases:
        conversation = request(f"/deployments/{deployment['deployment_id']}/conversations", "POST", {"title": question[:30]})
        state, detail = run_case(conversation, question)
        completed_tools = [event["data"].get("tool", "") for event in detail["events"] if event["event"] == "tool.completed"]
        assert any(name.startswith(expected_tool_prefix) for name in completed_tools), completed_tools
        assert any(event["event"] == expected_event for event in detail["events"]), expected_event
        output = next(event["data"].get("content") for event in reversed(detail["events"]) if event["event"] == "runtime.output")
        assert output and "已完成业务查询" in output
        case_results.append({"question": question, "run_id": state["run_id"], "tools": completed_tools, "output": output})

    history_conversation = request(f"/deployments/{deployment['deployment_id']}/conversations", "POST", {"title": "会话历史验收"})
    _, history_seed = run_case(history_conversation, "项目代号是星河")
    _, history_answer = run_case(history_conversation, "项目代号是什么？")
    history_output = next(event["data"].get("content") for event in reversed(history_answer["events"]) if event["event"] == "runtime.output")
    assert history_output == "当前会话中的项目代号是星河。"
    history_loaded = next(event for event in history_answer["events"] if event["event"] == "conversation.history.loaded")
    assert history_loaded["data"]["count"] == 2

    report = {
        "status": "PASSED", "deployment_id": deployment["deployment_id"],
        "revision_number": published["revision_number"], "discovered_mcp_tools": [item["name"] for item in discovered_tools],
        "discovered_ragflow_datasets": [item["name"] for item in datasets],
        "local_knowledge": {"documents": ["employee-attendance.pdf", "员工考勤补充规定.docx"], "retrieval_hits": len(local_hits)},
        "memory": {"memory_id": memory_item["memory_id"], "loaded_in_every_run": True},
        "conversation_history": {"loaded_messages": history_loaded["data"]["count"], "answer": history_output},
        "cases": case_results,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
