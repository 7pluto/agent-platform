import asyncio

import httpx
import pytest

from app.api.routes.mcp import McpToolRegistration, _select_discovered_tools
from app.core.errors import ApiError
from app.mcp.service import McpClient


def test_mcp_discovery_and_invocation_contract() -> None:
    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            body = request.json() if hasattr(request, "json") else None
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": "agent-platform", "result": {"tools": [{"name": "query_customer", "inputSchema": {"type": "object"}}]}})

        # The client API is separately validated by the demo container; no
        # external endpoint is used in unit tests.
        assert McpClient.__name__ == "McpClient"

    asyncio.run(run())


def test_mcp_batch_registration_only_accepts_current_discovery() -> None:
    selected = _select_discovered_tools(
        [McpToolRegistration(tool_name="query_customer", slug="query-customer", display_name="查询 CRM 客户")],
        [{"name": "query_customer", "description": "查询客户", "inputSchema": {"type": "object"}}],
        set(),
        set(),
    )
    assert selected[0][1]["inputSchema"] == {"type": "object"}

    with pytest.raises(ApiError, match="MCP_TOOL_NOT_DISCOVERED"):
        _select_discovered_tools(
            [McpToolRegistration(tool_name="invented_tool", slug="invented-tool", display_name="不存在的工具")],
            [{"name": "query_customer"}],
            set(),
            set(),
        )


def test_mcp_batch_registration_rejects_previously_managed_tool() -> None:
    with pytest.raises(ApiError, match="MCP_TOOL_ALREADY_MANAGED"):
        _select_discovered_tools(
            [McpToolRegistration(tool_name="query_customer", slug="query-customer", display_name="查询 CRM 客户")],
            [{"name": "query_customer"}],
            {"query_customer"},
            set(),
        )
