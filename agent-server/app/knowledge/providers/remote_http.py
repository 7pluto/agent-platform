"""Fixed-contract adapter for an existing enterprise HTTP knowledge service."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode, urljoin

import httpx

from app.core.errors import ApiError
from app.iam.models import Principal
from app.knowledge.providers.base import KnowledgeHit, KnowledgeProvider, KnowledgeSearchResult
from app.mcp.service import mcp_auth_headers
from app.outbound.safe_http import OutboundPolicy, safe_http_client


def _path(value: Any, path: str, default: Any = None) -> Any:
    current = value
    for key in path.split(".") if path else []:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return current if current is not None else default


class RemoteHttpKnowledgeProvider(KnowledgeProvider):
    provider_name = "REMOTE_HTTP"

    def __init__(self, principal: Principal) -> None:
        self.principal = principal

    async def search(self, *, knowledge_version_id: str, config: dict[str, Any], query: str, top_k: int) -> KnowledgeSearchResult:
        endpoint = str(config["endpoint"]).rstrip("/") + "/"
        target = urljoin(endpoint, str(config.get("search_path", "/search")).lstrip("/"))
        request_mapping = dict(config.get("request_mapping") or {})
        body = dict(request_mapping.get("static_body") or {})
        body[str(request_mapping.get("query_field", "query"))] = query
        body[str(request_mapping.get("top_k_field", "top_k"))] = top_k
        if config.get("method", "POST") == "GET":
            target = f"{target}?{urlencode(body, doseq=True)}"
            body = None
        headers = await mcp_auth_headers(config, self.principal.tenant_id, self.principal.external_user_id)
        try:
            response = await safe_http_client.request(str(config.get("method", "POST")), target, policy=OutboundPolicy.from_config(config, default_timeout=15), headers=headers or None, json_body=body)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise ApiError(502, "REMOTE_KNOWLEDGE_UPSTREAM_ERROR", f"remote knowledge returned {exc.response.status_code}") from exc
        except ValueError as exc:
            raise ApiError(502, "REMOTE_KNOWLEDGE_INVALID_RESPONSE", "remote knowledge response must be JSON") from exc
        mapping = dict(config.get("response_mapping") or {})
        items = _path(payload, str(mapping.get("items_path", "items")), [])
        if not isinstance(items, list):
            raise ApiError(502, "REMOTE_KNOWLEDGE_INVALID_RESPONSE", "remote knowledge items path is not a list")
        content_field = str(mapping.get("content_field", "content"))
        hits = [KnowledgeHit(id=str(item.get(str(mapping.get("id_field", "id")), index)), content=str(item.get(content_field, "")), score=float(item[mapping["score_field"]]) if mapping.get("score_field") and item.get(mapping["score_field"]) is not None else None, title=str(item.get(mapping.get("title_field", "title"), "")) or None, source="REMOTE_HTTP", metadata=item.get(mapping.get("metadata_field", "metadata"), {}) if isinstance(item.get(mapping.get("metadata_field", "metadata"), {}), dict) else {}) for index, item in enumerate(items[:top_k]) if isinstance(item, dict) and item.get(content_field) is not None]
        return KnowledgeSearchResult(provider=self.provider_name, hits=hits, metadata={"knowledge_version_id": knowledge_version_id, "result_count": len(hits)})
