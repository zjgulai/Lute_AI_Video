"""Private runtime wiring for authorized-live poyo submitter."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol
from urllib import request

from src.pipeline.authorized_live_poyo_submitter import (
    AUTHORIZED_LIVE_POYO_TRANSPORT_ENV,
    AuthorizedLivePoyoPayload,
    AuthorizedLivePoyoSubmitter,
    PoyoSubmitPollHttpClient,
    build_authorized_live_poyo_submitter_from_http,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
POYO_API_KEY_ENV = "POYO_API_KEY"
POYO_API_BASE_URL_ENV = "POYO_API_BASE_URL"
AUTHORIZED_LIVE_POYO_PAYLOADS_ENV = "AI_VIDEO_AUTHORIZED_LIVE_POYO_PAYLOADS"
DEFAULT_POYO_API_BASE_URL = "https://api.poyo.ai"


class UrlOpenResponse(Protocol):
    def __enter__(self) -> UrlOpenResponse: ...

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None: ...

    def read(self) -> bytes: ...


class UrlOpen(Protocol):
    def __call__(self, http_request: request.Request, *, timeout: float) -> UrlOpenResponse: ...


HttpClientFactory = Callable[[str], PoyoSubmitPollHttpClient]


class AuthorizedLivePoyoHttpClient:
    """Minimal JSON HTTP client used only after authorized-live gates pass."""

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 90.0,
        urlopen: UrlOpen | None = None,
    ) -> None:
        if not base_url:
            raise ValueError("poyo base_url is required")
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._urlopen = urlopen or request.urlopen

    def post_json(
        self,
        *,
        path: str,
        headers: Mapping[str, str],
        body: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        payload = json.dumps(dict(body), ensure_ascii=False).encode("utf-8")
        http_request = request.Request(
            f"{self._base_url}{path}",
            data=payload,
            headers=dict(headers),
            method="POST",
        )
        return self._request_json(http_request)

    def get_json(
        self,
        *,
        path: str,
        headers: Mapping[str, str],
    ) -> Mapping[str, Any]:
        http_request = request.Request(
            f"{self._base_url}{path}",
            headers=dict(headers),
            method="GET",
        )
        return self._request_json(http_request)

    def _request_json(self, http_request: request.Request) -> Mapping[str, Any]:
        with self._urlopen(http_request, timeout=self._timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError("poyo HTTP response must be a JSON object")
        return payload


def build_authorized_live_poyo_runtime_submitter(
    *,
    env: Mapping[str, str],
    http_client_factory: HttpClientFactory | None = None,
) -> AuthorizedLivePoyoSubmitter | None:
    """Build a poyo submitter from private runtime env without default side effects."""
    if env.get(AUTHORIZED_LIVE_POYO_TRANSPORT_ENV) != "1":
        return None
    authorization_token = env.get(POYO_API_KEY_ENV, "")
    if not authorization_token:
        raise ValueError(f"{POYO_API_KEY_ENV} is required for authorized-live poyo submitter")

    payloads_path = env.get(AUTHORIZED_LIVE_POYO_PAYLOADS_ENV, "")
    if not payloads_path:
        raise ValueError(f"{AUTHORIZED_LIVE_POYO_PAYLOADS_ENV} is required for authorized-live poyo submitter")

    payloads = load_authorized_live_poyo_payloads(payloads_path)
    base_url = (env.get(POYO_API_BASE_URL_ENV) or DEFAULT_POYO_API_BASE_URL).rstrip("/")
    factory = http_client_factory or (lambda url: AuthorizedLivePoyoHttpClient(base_url=url))
    http_client = factory(base_url)
    return build_authorized_live_poyo_submitter_from_http(
        env=env,
        authorization_token=authorization_token,
        http_client=http_client,
        payloads=payloads,
    )


def load_authorized_live_poyo_payloads(path: str | Path) -> dict[str, AuthorizedLivePoyoPayload]:
    """Load private poyo prompt payloads from tmp/ or outside the repository."""
    resolved = Path(path).expanduser().resolve()
    repo_root = REPO_ROOT.resolve()
    repo_tmp = (REPO_ROOT / "tmp").resolve()
    if resolved.is_relative_to(repo_root) and not resolved.is_relative_to(repo_tmp):
        raise ValueError("private poyo payloads must be under tmp/ or outside the repository")
    if not resolved.is_file():
        raise ValueError(f"private poyo payloads file not found: {resolved}")

    raw = json.loads(resolved.read_text())
    payload_items = raw.get("payloads") if isinstance(raw, Mapping) else None
    if not isinstance(payload_items, list) or not payload_items:
        raise ValueError("private poyo payloads must contain a non-empty payloads list")

    payloads: dict[str, AuthorizedLivePoyoPayload] = {}
    for item in payload_items:
        payload = AuthorizedLivePoyoPayload.model_validate(item)
        if payload.job_id in payloads:
            raise ValueError(f"duplicate private poyo payload job_id: {payload.job_id}")
        payloads[payload.job_id] = payload
    return payloads
