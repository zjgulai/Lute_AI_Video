"""Local-only Alertmanager webhook sink used by the monitoring compose profile."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar


class AlertReceiver(BaseHTTPRequestHandler):
    """Accept bounded Alertmanager JSON without logging payload contents."""

    server_version = "ai-video-monitoring-fixture/1"
    protocol_version = "HTTP/1.1"
    max_body_bytes: ClassVar[int] = 1_048_576

    def do_POST(self) -> None:
        if self.path != "/alerts":
            self._reply(HTTPStatus.NOT_FOUND)
            return
        raw_length = self.headers.get("Content-Length")
        try:
            content_length = int(raw_length or "")
        except ValueError:
            self._reply(HTTPStatus.BAD_REQUEST)
            return
        if content_length <= 0 or content_length > self.max_body_bytes:
            self._reply(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return
        payload = self.rfile.read(content_length)
        try:
            parsed = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._reply(HTTPStatus.BAD_REQUEST)
            return
        if not isinstance(parsed, dict) or not isinstance(parsed.get("alerts"), list):
            self._reply(HTTPStatus.UNPROCESSABLE_ENTITY)
            return
        self._reply(HTTPStatus.OK)

    def log_message(self, format: str, *args: object) -> None:
        del format, args

    def _reply(self, status: HTTPStatus) -> None:
        body = b"{}\n"
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", 8080), AlertReceiver)
    server.serve_forever()


if __name__ == "__main__":
    main()
