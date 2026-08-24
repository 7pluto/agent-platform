#!/usr/bin/env python3
"""Serve the production Console bundle and proxy /api for local browser QA."""

from __future__ import annotations

import argparse
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import mimetypes
from pathlib import Path
from urllib.parse import urlsplit


HOP_BY_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "transfer-encoding", "upgrade"}


class Handler(BaseHTTPRequestHandler):
    root: Path
    api_host: str
    api_port: int

    def _handle(self) -> None:
        if self.path.startswith("/api/"):
            self._proxy()
        else:
            self._static()

    def _proxy(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else None
        headers = {key: value for key, value in self.headers.items() if key.lower() not in HOP_BY_HOP and key.lower() != "host"}
        connection = http.client.HTTPConnection(self.api_host, self.api_port, timeout=240)
        try:
            connection.request(self.command, self.path, body=body, headers=headers)
            response = connection.getresponse()
            self.send_response(response.status)
            for key, value in response.getheaders():
                if key.lower() not in HOP_BY_HOP:
                    self.send_header(key, value)
            self.end_headers()
            while chunk := response.read(64 * 1024):
                self.wfile.write(chunk)
                self.wfile.flush()
        finally:
            connection.close()

    def _static(self) -> None:
        relative = urlsplit(self.path).path.lstrip("/") or "index.html"
        candidate = (self.root / relative).resolve()
        if self.root not in candidate.parents and candidate != self.root:
            self.send_error(403); return
        if not candidate.is_file():
            candidate = self.root / "index.html"
        data = candidate.read_bytes()
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
            content_type += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD": self.wfile.write(data)

    do_GET = _handle
    do_POST = _handle
    do_PUT = _handle
    do_PATCH = _handle
    do_DELETE = _handle
    do_HEAD = _handle

    def log_message(self, *_args) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="agent-console/dist")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4173)
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    api = urlsplit(args.api)
    Handler.root = Path(args.root).resolve()
    Handler.api_host = api.hostname or "127.0.0.1"
    Handler.api_port = api.port or 80
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
