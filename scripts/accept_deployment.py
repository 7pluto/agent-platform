#!/usr/bin/env python3
"""Create a Run through the public API contract and print a secret-safe event summary."""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import time
import urllib.error
import urllib.request
import uuid


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("deployment_id")
    parser.add_argument("message")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()

    cookies = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))

    def request(path: str, method: str = "GET", payload: dict | None = None, headers: dict | None = None):
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        all_headers = {"Accept": "application/json", **(headers or {})}
        if body is not None:
            all_headers["Content-Type"] = "application/json"
        req = urllib.request.Request(args.base_url + path, data=body, headers=all_headers, method=method)
        try:
            with opener.open(req, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {path} failed with HTTP {exc.code}: {detail}") from exc

    login = request("/auth/exchange", "POST", {"ticket_code": "dev-ticket"})
    csrf = login["csrf_token"]
    conversation_session = request(
        f"/deployments/{args.deployment_id}/conversations",
        "POST",
        {"title": f"CLI 验收 {time.strftime('%Y-%m-%d %H:%M:%S')}"},
        {"X-CSRF-Token": csrf},
    )
    conversation_id = conversation_session["conversation"]["conversation_id"]
    thread_id = conversation_session["thread"]["thread_id"]
    run = request(
        f"/deployments/{args.deployment_id}/runs",
        "POST",
        {
            "deployment_id": args.deployment_id,
            "conversation_id": conversation_id,
            "thread_id": thread_id,
            "message": args.message,
        },
        {"X-CSRF-Token": csrf, "Idempotency-Key": f"acceptance-{uuid.uuid4()}"},
    )
    run_id = run["run_id"]
    deadline = time.monotonic() + args.timeout
    while True:
        status = request(f"/runs/{run_id}")["status"]
        if status in {"COMPLETED", "FAILED", "CANCELLED"}:
            break
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Run {run_id} did not finish within {args.timeout}s")
        time.sleep(2)

    detail = request(f"/runs/{run_id}/detail")
    events = detail["events"]
    summary = {
        "deployment_id": args.deployment_id,
        "run_id": run_id,
        "conversation_id": conversation_id,
        "thread_id": thread_id,
        "status": status,
        "manifest_hash": detail["manifest"]["manifest_hash"],
        "resource_types": sorted({item["type"] for item in detail["manifest"]["resources"]}),
        "secret_reference_schemes": sorted({value.split("://", 1)[0] for value in detail["manifest"]["secret_refs"].values()}),
        "tools_completed": [event["data"].get("tool") for event in events if event["event"] == "tool.completed"],
        "invalid_tool_argument_retries": sum(event["event"] == "tool.arguments.invalid" for event in events),
        "dify_flow_events": sum(event["event"] == "dify.flow.completed" for event in events),
        "dify_rag_events": sum(event["event"] == "dify.rag.retrieved" for event in events),
        "platform_rag_events": sum(event["event"] == "rag.retrieved" for event in events),
        "memory_read_events": sum(event["event"] == "memory.read" for event in events),
        "failure": next((event["data"] for event in reversed(events) if event["event"] == "runtime.failed"), None),
        "output": next((event["data"].get("content") for event in reversed(events) if event["event"] == "runtime.output"), None),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if status != "COMPLETED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
