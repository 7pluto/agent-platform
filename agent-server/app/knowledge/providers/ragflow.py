"""RAGFlow dataset discovery and fixed-dataset retrieval provider."""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import httpx

from app.core.errors import ApiError
from app.iam.models import Principal
from app.knowledge.providers.base import KnowledgeHit, KnowledgeProvider, KnowledgeSearchResult
from app.mcp.service import mcp_auth_headers
from app.outbound.safe_http import OutboundPolicy, safe_http_client


class RagflowKnowledgeProvider(KnowledgeProvider):
    provider_name = "RAGFLOW"

    def __init__(self, principal: Principal) -> None:
        self.principal = principal

    async def discover_datasets(self, connection_config: dict[str, Any]) -> list[dict[str, Any]]:
        payload = await self._request("GET", connection_config, "/api/v1/datasets")
        data = payload.get("data", [])
        if not isinstance(data, list):
            raise ApiError(502, "RAGFLOW_INVALID_RESPONSE", "RAGFlow dataset discovery returned no dataset list")
        return [{"id": str(item.get("id", "")), "name": str(item.get("name", "")), "description": item.get("description")} for item in data if isinstance(item, dict) and item.get("id") and item.get("name")]

    async def search(self, *, knowledge_version_id: str, config: dict[str, Any], query: str, top_k: int) -> KnowledgeSearchResult:
        dataset_id = str(config["external_dataset_id"])
        payload = await self._request("POST", config, "/api/v1/retrieval", {"question": query, "dataset_ids": [dataset_id], "page": 1, "page_size": top_k, "top_k": top_k})
        data = payload.get("data", [])
        if not isinstance(data, list):
            raise ApiError(502, "RAGFLOW_INVALID_RESPONSE", "RAGFlow retrieval returned no chunk list")
        hits = [KnowledgeHit(id=str(item.get("id", index)), content=str(item.get("content", "")), score=float(item["similarity"]) if item.get("similarity") is not None else None, title=str(item.get("document_name") or item.get("document_id") or "") or None, source="RAGFLOW", metadata={"dataset_id": dataset_id, "document_id": item.get("document_id")}) for index, item in enumerate(data[:top_k]) if isinstance(item, dict) and item.get("content")]
        return KnowledgeSearchResult(provider=self.provider_name, hits=hits, metadata={"knowledge_version_id": knowledge_version_id, "dataset_id": dataset_id})

    async def _request(self, method: str, config: dict[str, Any], path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        target = urljoin(str(config["endpoint"]).rstrip("/") + "/", path.lstrip("/"))
        headers = await mcp_auth_headers(config, self.principal.tenant_id, self.principal.external_user_id)
        try:
            response = await safe_http_client.request(method, target, policy=OutboundPolicy.from_config(config, default_timeout=20), headers=headers or None, json_body=body)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise ApiError(502, "RAGFLOW_UPSTREAM_ERROR", f"RAGFlow returned {exc.response.status_code}") from exc
        except ValueError as exc:
            raise ApiError(502, "RAGFLOW_INVALID_RESPONSE", "RAGFlow response must be JSON") from exc
        if not isinstance(payload, dict) or int(payload.get("code", 0)) != 0:
            raise ApiError(502, "RAGFLOW_UPSTREAM_ERROR", str(payload.get("message", "RAGFlow request failed")) if isinstance(payload, dict) else "RAGFlow request failed")
        return payload
