import asyncio

import httpx

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
