"""Bounded public-read-only HTTP collector for the XMind performance gate."""

from __future__ import annotations

import datetime as dt
import gzip
import http.client
import io
import platform
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from typing import Any


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str,
                         headers: Any, newurl: str) -> None:
        return None


def fetch_transport_sample(opener: Any, route: dict[str, Any], origin: str) -> dict[str, Any]:
    url = urllib.parse.urljoin(origin, route["path"])
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Encoding": "gzip",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "User-Agent": "Lute-XMind-Performance-Gate/1.0",
        },
        method="GET",
    )
    started = time.perf_counter()
    try:
        with opener.open(request, timeout=20) as response:
            headers_at = time.perf_counter()
            encoded = response.read(int(route["max_encoded_bytes"]) + 1)
            finished = time.perf_counter()
            encoding = response.headers.get("Content-Encoding", "").lower()
            if encoding == "gzip":
                with gzip.GzipFile(fileobj=io.BytesIO(encoded)) as stream:
                    decoded = stream.read(int(route["max_decoded_bytes"]) + 1)
            elif encoding in ("", "identity"):
                decoded = encoded
            else:
                decoded = b""
            marker = route["content_marker"].encode("utf-8") in decoded
            return {
                "status": response.status,
                "redirects": 0,
                "requested_url": url,
                "final_url": response.geturl(),
                "content_type": response.headers.get("Content-Type", ""),
                "content_encoding": encoding or "identity",
                "cache_control": response.headers.get("Cache-Control", ""),
                "content_marker_found": marker,
                "ttfb_ms": round((headers_at - started) * 1000, 1),
                "total_ms": round((finished - started) * 1000, 1),
                "encoded_bytes": len(encoded),
                "decoded_bytes": len(decoded),
            }
    except (OSError, EOFError, zlib.error, http.client.HTTPException, urllib.error.URLError) as exc:
        finished = time.perf_counter()
        code = getattr(exc, "code", 0)
        return {
            "status": code,
            "redirects": 1 if code in {301, 302, 303, 307, 308} else 0,
            "requested_url": url,
            "final_url": getattr(exc, "url", url),
            "content_type": "",
            "content_marker_found": False,
            "ttfb_ms": round((finished - started) * 1000, 1),
            "total_ms": round((finished - started) * 1000, 1),
            "encoded_bytes": 0,
            "decoded_bytes": 0,
            "error": f"{type(exc).__name__}: {exc}",
        }


def collect_transport_evidence(contract: dict[str, Any]) -> dict[str, Any]:
    opener = urllib.request.build_opener(NoRedirectHandler())
    routes: dict[str, list[dict[str, Any]]] = {}
    warmup_errors: list[str] = []
    for route in contract["routes"]:
        for _ in range(contract["sampling"]["warmups"]):
            sample = fetch_transport_sample(opener, route, contract["origin"])
            if sample.get("status") != 200:
                warmup_errors.append(f"{route['path']}: {sample.get('error', sample.get('status'))}")
        routes[route["path"]] = [
            fetch_transport_sample(opener, route, contract["origin"])
            for _ in range(contract["sampling"]["measured_runs"])
        ]
    return {
        "schema": "xmind-transport-evidence.v1",
        "origin": contract["origin"],
        "cache": "disabled",
        "captured_at_utc": dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z"),
        "runtime": {"python": platform.python_version(), "platform": platform.platform()},
        "warmup_errors": warmup_errors,
        "routes": routes,
    }
