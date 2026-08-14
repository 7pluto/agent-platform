from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.core.errors import ApiError
from app.core.secrets import resolve_env_secret, resolve_secret_reference
from app.outbound.safe_http import OutboundPolicy, safe_http_client


@dataclass(frozen=True)
class DifyFlowClient:
    """Restricted Dify App API adapter used by versioned Tool resources."""

    base_url: str
    api_key: str
    flow_type: str
    timeout_seconds: float
    egress_allowlist: tuple[str, ...] = ()

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "DifyFlowClient":
        return cls(
            base_url=str(config["base_url"]).rstrip("/"),
            api_key=resolve_env_secret(str(config["secret_ref"])),
            flow_type=str(config.get("flow_type", "CHATFLOW")).upper(),
            timeout_seconds=float(config.get("timeout_seconds", 60)),
            egress_allowlist=tuple(str(item) for item in config.get("egress_allowlist", [])),
        )

    @classmethod
    async def from_runtime_config(cls, config: dict[str, Any], tenant_id: str, user_id: str) -> "DifyFlowClient":
        return cls(
            base_url=str(config["base_url"]).rstrip("/"),
            api_key=await resolve_secret_reference(str(config["secret_ref"]), tenant_id, user_id),
            flow_type=str(config.get("flow_type", "CHATFLOW")).upper(),
            timeout_seconds=float(config.get("timeout_seconds", 60)),
            egress_allowlist=tuple(str(item) for item in config.get("egress_allowlist", [])),
        )

    def _outbound_policy(self) -> OutboundPolicy:
        # Published Tool config is validated to require egress_allowlist.  The
        # fallback only preserves the direct constructor used by isolated tests.
        host = urlsplit(self.base_url).hostname
        return OutboundPolicy(
            allowed_hosts=tuple(host.lower() for host in self.egress_allowlist) or ((host or "").lower(),),
            timeout_seconds=self.timeout_seconds,
        )

    async def invoke(self, arguments: dict[str, Any], *, user_id: str) -> dict[str, Any]:
        supplied_inputs = arguments.get("inputs", {})
        if supplied_inputs is None:
            supplied_inputs = {}
        if not isinstance(supplied_inputs, dict):
            raise ApiError(422, "DIFY_FLOW_INVALID_INPUT", "Dify Flow inputs must be an object")

        query = str(arguments.get("query", "")).strip()
        static_inputs = arguments.get("_static_inputs", {})
        inputs = {**static_inputs, **supplied_inputs} if isinstance(static_inputs, dict) else supplied_inputs
        if self.flow_type == "CHATFLOW":
            if not query:
                raise ApiError(422, "DIFY_FLOW_QUERY_REQUIRED", "Dify Chatflow requires query")
            path = "/chat-messages"
            payload = {
                "inputs": inputs,
                "query": query,
                "response_mode": "blocking",
                "user": user_id,
            }
        else:
            query_input_name = str(arguments.get("_query_input_name", "query"))
            if query:
                inputs.setdefault(query_input_name, query)
            path = "/workflows/run"
            payload = {"inputs": inputs, "response_mode": "blocking", "user": user_id}

        try:
            response = await safe_http_client.request(
                "POST",
                f"{self.base_url}{path}",
                json_body=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
                policy=self._outbound_policy(),
            )
            response.raise_for_status()
            body = response.json()
        except httpx.TimeoutException as exc:
            raise ApiError(504, "DIFY_FLOW_TIMEOUT", "Dify Flow request timed out") from exc
        except httpx.HTTPError as exc:
            raise ApiError(502, "DIFY_FLOW_UPSTREAM_UNAVAILABLE", "Dify Flow is unavailable") from exc
        if not isinstance(body, dict):
            raise ApiError(502, "DIFY_FLOW_INVALID_RESPONSE", "Dify Flow returned an invalid response")

        if self.flow_type == "CHATFLOW":
            answer = body.get("answer")
            if not isinstance(answer, str):
                raise ApiError(502, "DIFY_FLOW_INVALID_RESPONSE", "Dify Chatflow response has no answer")
            metadata = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}
            resources = metadata.get("retriever_resources", [])
            return {
                "answer": answer,
                "conversation_id": body.get("conversation_id"),
                "message_id": body.get("message_id"),
                "retriever_resources": resources if isinstance(resources, list) else [],
                "usage": metadata.get("usage") if isinstance(metadata.get("usage"), dict) else {},
            }

        data = body.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("outputs"), dict):
            raise ApiError(502, "DIFY_FLOW_INVALID_RESPONSE", "Dify Workflow response has no outputs")
        return {
            "outputs": data["outputs"],
            "workflow_run_id": body.get("workflow_run_id") or data.get("id"),
            "status": data.get("status"),
            "elapsed_time": data.get("elapsed_time"),
            "total_tokens": data.get("total_tokens"),
        }

    async def inspect_application(self) -> dict[str, Any]:
        """Validate the app credential and return its public input contract.

        Dify's parameters endpoint is read-only and works for apps whose
        workflow requires business inputs.  Using it for onboarding avoids
        rejecting a valid workflow merely because a synthetic test run cannot
        provide those required values.
        """
        try:
            response = await safe_http_client.request(
                "GET",
                f"{self.base_url}/parameters",
                headers={"Authorization": f"Bearer {self.api_key}"},
                policy=self._outbound_policy(),
            )
            response.raise_for_status()
            body = response.json()
        except httpx.TimeoutException as exc:
            raise ApiError(504, "DIFY_FLOW_TIMEOUT", "Dify application inspection timed out") from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            code = "DIFY_CREDENTIAL_REJECTED" if status in {401, 403} else "DIFY_FLOW_UPSTREAM_UNAVAILABLE"
            raise ApiError(502, code, "Dify application could not be inspected") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise ApiError(502, "DIFY_FLOW_UPSTREAM_UNAVAILABLE", "Dify application could not be inspected") from exc
        if not isinstance(body, dict):
            raise ApiError(502, "DIFY_FLOW_INVALID_RESPONSE", "Dify parameters response is invalid")
        inputs = body.get("user_input_form", [])
        if not isinstance(inputs, list):
            inputs = []
        return {
            "available": True,
            "flow_type": self.flow_type,
            "input_form": inputs,
            "file_upload": body.get("file_upload") if isinstance(body.get("file_upload"), dict) else {},
            "opening_statement": body.get("opening_statement") if isinstance(body.get("opening_statement"), str) else None,
            "suggested_questions": body.get("suggested_questions") if isinstance(body.get("suggested_questions"), list) else [],
        }

    async def test_connection(self, test_query: str = "请回复 OK") -> dict[str, Any]:
        inspection = await self.inspect_application()
        # Chatflows accept a plain query, so exercise the complete invocation
        # path. Workflows may declare arbitrary required inputs; inspection is
        # the safe connection test until an operator supplies a real test case.
        if self.flow_type == "CHATFLOW":
            result = await self.invoke({"query": test_query}, user_id="agent-platform-connection-test")
            inspection["has_retrieval"] = bool(result.get("retriever_resources"))
            inspection["invocation_tested"] = True
        else:
            inspection["has_retrieval"] = False
            inspection["invocation_tested"] = False
        return inspection
