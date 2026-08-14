"""Small read-only Streamable HTTP-compatible demonstration service.

It is intentionally internal-only; real CRM credentials and write methods are
not part of the V1 demonstration path.
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json


TOOLS = [{"name": "query_customer", "description": "Look up a demonstration customer by id", "inputSchema": {"type": "object", "properties": {"customer_id": {"type": "string"}}, "required": ["customer_id"]}}]


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/mcp":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(length) or b"{}")
        method = request.get("method")
        if method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call" and request.get("params", {}).get("name") == "query_customer":
            identifier = request.get("params", {}).get("arguments", {}).get("customer_id", "unknown")
            result = {"content": [{"type": "text", "text": json.dumps({"customer_id": identifier, "name": "Demo Customer", "tier": "standard"})}]}
        else:
            self.send_response(400); self.end_headers(); return
        response = json.dumps({"jsonrpc": "2.0", "id": request.get("id"), "result": result}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(response))); self.end_headers(); self.wfile.write(response)

    def log_message(self, *_):
        return


HTTPServer(("0.0.0.0", 8090), Handler).serve_forever()
