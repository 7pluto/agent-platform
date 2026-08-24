"""Small read-only Streamable HTTP-compatible demonstration service.

It is intentionally internal-only; real CRM credentials and write methods are
not part of the V1 demonstration path.
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json


TOOLS = [
    {"name": "query_customer", "description": "按客户编号查询 CRM 客户基本信息", "inputSchema": {"type": "object", "properties": {"customer_id": {"type": "string", "description": "客户编号"}}, "required": ["customer_id"]}},
    {"name": "list_customer_orders", "description": "查询 CRM 客户最近订单", "inputSchema": {"type": "object", "properties": {"customer_id": {"type": "string", "description": "客户编号"}, "limit": {"type": "integer", "minimum": 1, "maximum": 10, "default": 3}}, "required": ["customer_id"]}},
]


def route(request):
    method = request.get("method")
    if method == "tools/list":
        return 200, {"tools": TOOLS}
    if method == "tools/call" and request.get("params", {}).get("name") == "query_customer":
        identifier = request.get("params", {}).get("arguments", {}).get("customer_id", "unknown")
        return 200, {"content": [{"type": "text", "text": json.dumps({"customer_id": identifier, "name": "示例客户", "tier": "重点客户"}, ensure_ascii=False)}]}
    if method == "tools/call" and request.get("params", {}).get("name") == "list_customer_orders":
        arguments = request.get("params", {}).get("arguments", {})
        identifier = arguments.get("customer_id", "unknown")
        limit = max(1, min(int(arguments.get("limit", 3)), 10))
        orders = [{"order_id": f"O-{index + 1:04d}", "customer_id": identifier, "amount": 1200 + index * 100, "status": "已完成"} for index in range(limit)]
        return 200, {"content": [{"type": "text", "text": json.dumps({"orders": orders}, ensure_ascii=False)}]}
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
        self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Length", str(len(response))); self.end_headers(); self.wfile.write(response)

    def log_message(self, *_):
        return


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8090), Handler).serve_forever()
