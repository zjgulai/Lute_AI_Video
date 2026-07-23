from __future__ import annotations

import http.client
import json
import threading
from http import HTTPStatus
from http.server import ThreadingHTTPServer

from scripts.monitoring_fixture_receiver import AlertReceiver


def _post(server: ThreadingHTTPServer, path: str, payload: bytes) -> int:
    host, port = server.server_address[:2]
    assert isinstance(host, str)
    assert isinstance(port, int)
    connection = http.client.HTTPConnection(host, port, timeout=2)
    connection.request(
        "POST",
        path,
        body=payload,
        headers={"Content-Type": "application/json"},
    )
    response = connection.getresponse()
    response.read()
    connection.close()
    return response.status


def test_receiver_accepts_firing_and_resolved_alertmanager_payloads() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), AlertReceiver)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for status in ("firing", "resolved"):
            payload = json.dumps({"status": status, "alerts": [{"status": status}]}).encode()
            assert _post(server, "/alerts", payload) == HTTPStatus.OK
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_receiver_rejects_wrong_path_and_malformed_payload() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), AlertReceiver)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert _post(server, "/wrong", b"{}") == HTTPStatus.NOT_FOUND
        assert _post(server, "/alerts", b"not-json") == HTTPStatus.BAD_REQUEST
        assert _post(server, "/alerts", b"{}") == HTTPStatus.UNPROCESSABLE_ENTITY
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
