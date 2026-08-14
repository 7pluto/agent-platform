from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

import httpx

from app.core.errors import ApiError
from app.core.secrets import resolve_secret_reference
from app.outbound.safe_http import OutboundPolicy, safe_http_client


class McpClient:
    """Minimal JSON-RPC boundary for the V1 Streamable HTTP MCP adapter."""

    async def discover(self, endpoint: str, timeout_seconds: float = 10.0, headers: dict[str, str] | None = None, egress_allowlist: list[str] | tuple[str, ...] | None = None) -> list[dict[str, Any]]:
        response = await self._request(endpoint, "tools/list", {}, timeout_seconds, headers, egress_allowlist)
        tools = response.get("tools")
        if not isinstance(tools, list):
            raise ApiError(502, "MCP_INVALID_RESPONSE", "MCP tools/list response is invalid")
        return [item for item in tools if isinstance(item, dict) and isinstance(item.get("name"), str)]

    async def discover_payload(self, endpoint: str, timeout_seconds: float = 10.0) -> list[dict[str, Any]]:
        """Testable implementation hook for HTTP discovery."""
        return await self.discover(endpoint, timeout_seconds)

    async def invoke(self, endpoint: str, name: str, arguments: dict[str, Any], timeout_seconds: float = 10.0, headers: dict[str, str] | None = None, egress_allowlist: list[str] | tuple[str, ...] | None = None) -> dict[str, Any]:
        return await self._request(endpoint, "tools/call", {"name": name, "arguments": arguments}, timeout_seconds, headers, egress_allowlist)

    async def _request(self, endpoint: str, method: str, params: dict[str, Any], timeout_seconds: float, headers: dict[str, str] | None = None, egress_allowlist: list[str] | tuple[str, ...] | None = None) -> dict[str, Any]:
        try:
            host = urlsplit(endpoint).hostname or ""
            policy = OutboundPolicy(
                allowed_hosts=tuple(str(item).lower().rstrip(".") for item in (egress_allowlist or [host])),
                timeout_seconds=timeout_seconds,
            )
            reply = await safe_http_client.request(
                "POST",
                endpoint,
                json_body={"jsonrpc": "2.0", "id": "agent-platform", "method": method, "params": params},
                headers=headers,
                policy=policy,
            )
            reply.raise_for_status()
            payload = reply.json()
        except httpx.HTTPError as exc:
            raise ApiError(502, "MCP_UPSTREAM_UNAVAILABLE", "MCP endpoint is unavailable") from exc
        if not isinstance(payload, dict) or "error" in payload or not isinstance(payload.get("result"), dict):
            raise ApiError(502, "MCP_INVALID_RESPONSE", "MCP returned an invalid response")
        return payload["result"]


mcp_client = McpClient()


async def mcp_auth_headers(config: dict[str, Any], tenant_id: str, user_id: str) -> dict[str, str]:
    secret_ref = config.get("secret_ref")
    if not secret_ref:
        return {}
    value = await resolve_secret_reference(str(secret_ref), tenant_id, user_id)
    header = str(config.get("auth_header", "Authorization"))
    scheme = str(config.get("auth_scheme", "Bearer")).strip()
    return {header: f"{scheme} {value}".strip()}
