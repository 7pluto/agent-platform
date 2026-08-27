from fastapi.testclient import TestClient

from app.api.routes import mcp
from app.main import app


def _admin_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/api/v1/auth/exchange", json={"ticket_code": "dev-ticket"})
    assert response.status_code == 200, response.text
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def _developer_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/api/v1/auth/exchange", json={"ticket_code": "dev-developer-ticket"})
    assert response.status_code == 200, response.text
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def _tools_for(endpoint: str) -> list[dict]:
    if "demo-crm-mcp" in endpoint:
        return [
            {"name": "query_customer", "description": "query customer", "inputSchema": {"type": "object", "properties": {"customer_id": {"type": "string"}}, "required": ["customer_id"]}},
            {"name": "list_customer_orders", "description": "list orders", "inputSchema": {"type": "object", "properties": {"customer_id": {"type": "string"}}, "required": ["customer_id"]}},
        ]
    if "demo-ticket-mcp" in endpoint:
        return [
            {"name": "query_ticket", "description": "query ticket", "inputSchema": {"type": "object", "properties": {"ticket_id": {"type": "string"}}, "required": ["ticket_id"]}},
            {"name": "list_customer_tickets", "description": "list tickets", "inputSchema": {"type": "object", "properties": {"customer_id": {"type": "string"}}, "required": ["customer_id"]}},
            {"name": "search_tickets", "description": "search tickets", "inputSchema": {"type": "object", "properties": {"keyword": {"type": "string"}}, "required": ["keyword"]}},
        ]
    if "demo-ops-mcp" in endpoint:
        return [
            {"name": "get_service_status", "description": "service status", "inputSchema": {"type": "object", "properties": {"service_name": {"type": "string"}}, "required": ["service_name"]}},
            {"name": "list_recent_incidents", "description": "recent incidents", "inputSchema": {"type": "object", "properties": {"service_name": {"type": "string"}}}},
            {"name": "get_incident", "description": "incident detail", "inputSchema": {"type": "object", "properties": {"incident_id": {"type": "string"}}, "required": ["incident_id"]}},
        ]
    raise AssertionError(f"unexpected MCP endpoint: {endpoint}")


def test_common_mcp_installer_creates_three_connections_and_eight_tools(monkeypatch) -> None:
    async def fake_discover(endpoint: str, timeout_seconds: float, headers: dict, allowlist: list[str]) -> list[dict]:
        assert timeout_seconds == 5
        assert allowlist
        return _tools_for(endpoint)

    monkeypatch.setattr(mcp.mcp_client, "discover", fake_discover)

    with TestClient(app, base_url="https://testserver") as client:
        admin_headers = _admin_headers(client)
        first = client.post("/api/v1/admin/common-mcp/install", headers=admin_headers)
        assert first.status_code == 200, first.text
        payload = first.json()
        assert payload["failed"] == 0
        assert payload["created_connections"] == 3
        assert payload["existing_connections"] == 0
        assert payload["created_tools"] == 8
        assert payload["existing_tools"] == 0
        assert len([item for item in payload["items"] if item["kind"] == "CONNECTION"]) == 3
        assert len([item for item in payload["items"] if item["kind"] == "TOOL"]) == 8

        second = client.post("/api/v1/admin/common-mcp/install", headers=admin_headers)
        assert second.status_code == 200, second.text
        second_payload = second.json()
        assert second_payload["failed"] == 0
        assert second_payload["created_connections"] == 0
        assert second_payload["existing_connections"] == 3
        assert second_payload["created_tools"] == 0
        assert second_payload["existing_tools"] == 8

        _developer_headers(client)
        available = client.get("/api/v1/developer/resources/available")
        assert available.status_code == 200, available.text
        mcp_tools = [
            item for item in available.json()
            if item["resource_type"] == "TOOL" and item.get("source_type") == "MCP" and "common-resource" in item.get("tags", [])
        ]
        assert len(mcp_tools) >= 8
        names = {item["display_name"] for item in mcp_tools}
        assert {"查询 CRM 客户", "查询工单详情", "查询服务状态"}.issubset(names)
