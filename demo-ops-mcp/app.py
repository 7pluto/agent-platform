"""Read-only operations MCP used by the development starter pack."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json


TOOLS = [
    {
        "name": "get_service_status",
        "description": "查询服务当前健康状态、延迟和错误率",
        "inputSchema": {
            "type": "object",
            "properties": {"service_name": {"type": "string", "description": "服务名称"}},
            "required": ["service_name"],
        },
    },
    {
        "name": "list_recent_incidents",
        "description": "查询近期运维故障事件",
        "inputSchema": {
            "type": "object",
            "properties": {
                "service_name": {"type": "string", "description": "可选服务名称"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
            },
        },
    },
    {
        "name": "get_incident",
        "description": "按事件编号查询故障详情和当前处置状态",
        "inputSchema": {
            "type": "object",
            "properties": {"incident_id": {"type": "string", "description": "故障事件编号"}},
            "required": ["incident_id"],
        },
    },
]


def _incident(incident_id: str, service_name: str = "agent-api") -> dict:
    return {
        "incident_id": incident_id,
        "service_name": service_name,
        "severity": "P2",
        "status": "已恢复",
        "summary": "上游依赖抖动导致部分请求超时",
        "started_at": "2026-08-27T02:10:00Z",
        "resolved_at": "2026-08-27T02:24:00Z",
    }


def route(request):
    method = request.get("method")
    params = request.get("params", {})
    arguments = params.get("arguments", {})
    name = params.get("name")
    if method == "tools/list":
        return 200, {"tools": TOOLS}
    if method == "tools/call" and name == "get_service_status":
        service_name = arguments.get("service_name", "unknown")
        payload = {"service_name": service_name, "status": "healthy", "latency_ms_p95": 82, "error_rate": 0.003, "checked_at": "2026-08-27T07:00:00Z"}
        return 200, {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]}
    if method == "tools/call" and name == "list_recent_incidents":
        service_name = arguments.get("service_name") or "agent-api"
        limit = max(1, min(int(arguments.get("limit", 5)), 10))
        incidents = [_incident(f"INC-{index + 1:04d}", service_name) for index in range(limit)]
        return 200, {"content": [{"type": "text", "text": json.dumps({"incidents": incidents}, ensure_ascii=False)}]}
    if method == "tools/call" and name == "get_incident":
        return 200, {"content": [{"type": "text", "text": json.dumps(_incident(arguments.get("incident_id", "INC-UNKNOWN")), ensure_ascii=False)}]}
    return 400, {"error": {"code": -32601, "message": "method or tool not found"}}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/mcp":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(length) or b"{}")
        status, result = route(request)
        envelope = {"jsonrpc": "2.0", "id": request.get("id")}
        envelope["result" if status == 200 else "error"] = result if status == 200 else result["error"]
        response = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, *_):
        return


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8093), Handler).serve_forever()
