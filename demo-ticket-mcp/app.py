"""Read-only ticket-system MCP used by the development starter pack."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json


TOOLS = [
    {
        "name": "query_ticket",
        "description": "按工单编号查询工单状态、优先级和处理信息",
        "inputSchema": {
            "type": "object",
            "properties": {"ticket_id": {"type": "string", "description": "工单编号"}},
            "required": ["ticket_id"],
        },
    },
    {
        "name": "list_customer_tickets",
        "description": "查询指定客户最近的工单",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "客户编号"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
            },
            "required": ["customer_id"],
        },
    },
    {
        "name": "search_tickets",
        "description": "按关键词和可选状态检索工单",
        "inputSchema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "工单标题或问题关键词"},
                "status": {"type": "string", "description": "可选状态，例如处理中、已完成"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
            },
            "required": ["keyword"],
        },
    },
]


def _ticket(ticket_id: str) -> dict:
    return {
        "ticket_id": ticket_id,
        "status": "处理中",
        "priority": "P2",
        "owner": "示例处理组",
        "summary": "客户反馈业务办理后状态未及时同步",
        "updated_at": "2026-08-27T06:30:00Z",
    }


def route(request):
    method = request.get("method")
    params = request.get("params", {})
    arguments = params.get("arguments", {})
    name = params.get("name")
    if method == "tools/list":
        return 200, {"tools": TOOLS}
    if method == "tools/call" and name == "query_ticket":
        return 200, {"content": [{"type": "text", "text": json.dumps(_ticket(arguments.get("ticket_id", "T-UNKNOWN")), ensure_ascii=False)}]}
    if method == "tools/call" and name == "list_customer_tickets":
        customer_id = arguments.get("customer_id", "unknown")
        limit = max(1, min(int(arguments.get("limit", 5)), 10))
        tickets = [{**_ticket(f"T-{index + 1:04d}"), "customer_id": customer_id} for index in range(limit)]
        return 200, {"content": [{"type": "text", "text": json.dumps({"tickets": tickets}, ensure_ascii=False)}]}
    if method == "tools/call" and name == "search_tickets":
        keyword = arguments.get("keyword", "")
        status = arguments.get("status") or "处理中"
        limit = max(1, min(int(arguments.get("limit", 5)), 10))
        tickets = [{**_ticket(f"S-{index + 1:04d}"), "status": status, "matched_keyword": keyword} for index in range(limit)]
        return 200, {"content": [{"type": "text", "text": json.dumps({"tickets": tickets}, ensure_ascii=False)}]}
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
    HTTPServer(("0.0.0.0", 8092), Handler).serve_forever()
