# W1-24 Publish Connector Truth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task in the main thread. The user explicitly prohibited subagents for this item. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make TikTok/Shopify publish and distribution-status paths fail closed whenever credential, simulation truth, or provider outcome truth is missing, while preserving W1-23's single-use acceptance transaction and zero-retry boundary.

**Architecture:** Add a small typed connector-error vocabulary and one strict credential validator per platform. Reuse those validators in readiness, direct publish, direct status, and platform listing. Real connectors return exact `simulated: false`; `PublishAttemptService` validates `simulated` before `success` and durably separates post-consume not-ready, simulated, deterministic-failure, and ambiguous outcomes. The status router performs a second trust projection, and the legacy `PublishEngine` propagates typed failures instead of swallowing them.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, httpx, asyncpg, SQLite, pytest/pytest-asyncio, Ruff, PostgreSQL 18 disposable regression, Next.js 16, React 19, TypeScript, Vitest, ESLint.

## Global Constraints

- Approved specification: `docs/superpowers/specs/2026-07-14-publish-connector-truth-design.md` with `status: approved`.
- Scope is W1-24 only. W1-25 credential env/receipt truth, W1-26 live publish, production migration/deploy, delivery, reconciliation, immutable snapshots, and acceptance UI remain separate.
- Preserve the dirty Wave 1A/W1-22/W1-23 worktree. Before every write, inspect the scoped diff; do not reset, restore, reformat, delete, or overwrite unrelated changes.
- Do not use subagents. Final evidence therefore stops at `implementation_complete_local / independent_review_pending` with `independent_review=false` unless a later separately authorized independent review occurs.
- Do not read `.env`, `.env.prod`, `DDDD.pem`, or any credential file. Tests use explicit non-production fixture strings through `monkeypatch` only.
- Do not construct real HTTP clients in credential-failure tests. Do not run real connector/status/provider calls, SSH, production database operations, deploy, publish, delivery, or metrics live pull.
- No migration, table, column, publish-attempt status, dependency, runtime mock flag, or frontend product/UX change. The generated OpenAPI TypeScript file must follow the backend enum change through the existing generator.
- Runtime publish/status code must not contain `_mock_publish`, `_mock_status`, `tt_mock_`, `sp_mock_`, or a mock-store publish URL. `ALLOW_MOCK_MODE` must not affect publish/status readiness or execution.
- Connector mappings use exact booleans: `type(result["simulated"]) is bool`; real connector mappings use `False`; dependency-injected fakes use `True` only when intentionally testing the simulation guard.
- Keep W1-23 order unchanged: readiness → prepared attempt → acceptance consume → durable `acceptance_consumed` → artifact revalidation → at most one connector call → terminal persistence. Never retry or restore acceptance.
- Stable response/logging only: no token, provider body, exception text, traceback, product text, or absolute media path. Logs may contain stable event, platform, attempt/trace ID, HTTP status, and exception class.
- Every behavior change follows RED → confirm named expected failures → minimal GREEN → focused regression → Ruff/diff checkpoint.
- The generic Superpowers plan template recommends commits. Repository authorization overrides it: this plan contains no stage/commit/push/PR step; those actions require a later explicit user instruction.
- Fixed evidence boundary: `production unchanged`, `provider_call=false`, `real_connector_call=false`, `external_status_call=false`, `live_publish=false`, `database_write=local-test-only`.

## File Structure

### Create

- `tests/test_publish_connector_truth.py` — credential parity, runtime-mock removal, exact simulated truth, connector deterministic/ambiguous/status behavior, and no-network guards.
- `tests/test_distribution_status_truth.py` — authenticated status HTTP 503/502/200 projections, injected-result validation, safe errors, and zero publish-ledger calls.
- `tests/test_publish_engine_truth.py` — typed-error propagation, simulated-result rejection, exact ordering, and one-call behavior for the retained compatibility engine.
- `docs/runbooks/publish-connector-truth.md` — W1-24 operational failure semantics, no-retry rule, status behavior, rollback order, and W1-25/W1-26 boundary.
- `docs/workflows/enterprise-ai-content-all-scenarios-roadmap-20260711.md` — durable final status and evidence boundary, updated only after all mandatory local gates pass.

### Modify

- `src/connectors/base.py` — typed credential state and connector credential/outcome/status exceptions.
- `src/connectors/registry.py` — shared strict readiness projection; no mock-mode vocabulary or exception swallowing.
- `src/connectors/tiktok_connector.py` — strict token recheck, no runtime mock, exact real result truth, deterministic rejection versus ambiguous mutation, and fail-closed status.
- `src/connectors/shopify_connector.py` — canonical-then-legacy token selection, strict store hostname, no runtime mock, exact real result truth, deterministic rejection versus ambiguity, and fail-closed status.
- `src/connectors/publish_engine.py` — exact simulated projection and typed-exception propagation.
- `src/models/publish_attempt.py` — two approved post-consume error codes only.
- `src/services/publish_attempt.py` — `simulated`-first validation and typed post-consume failure mapping.
- `src/storage/publish_attempt_repository.py` — add the two approved codes only to the existing allowlists.
- `src/routers/distribution.py` — stable status 503/502 projection, result validation, and strict platform readiness listing.
- `tests/test_connectors_mock.py` — replace obsolete runtime-mock success expectations with fail-closed compatibility assertions.
- `tests/test_publish_connector_log_safety.py` — add `simulated=false`, typed ambiguity expectations, and explicit token plumbing without weakening log assertions.
- `tests/test_publish_attempt_contracts.py` — exact 13-code vocabulary.
- `tests/test_publish_attempt_repository.py` — new failed-state codes and wrong-state rejection.
- `tests/test_publish_attempt_pg18.py` — disposable PG18 terminal-code regression; no DDL change.
- `tests/test_publish_attempt_service.py` — fake result migration and complete outcome matrix.
- `tests/test_publish_acceptance_routes.py` — retain auth/OpenAPI regression; status-specific behavior moves to the new focused file.
- `tests/test_metrics_poller.py` — regression only; no metrics production logic change.
- `web/src/types/api.generated.ts` — generated-only addition of the two approved publish error enum values.
- `docs/runbooks/README.md`, `docs/reference/api-endpoints.md`, `docs/runbooks/publish-connector-truth.md`, `docs/workflows/enterprise-ai-content-all-scenarios-roadmap-20260711.md`, and `AGENTS.md` — synchronize only from fresh verified evidence.

### Explicitly Do Not Modify

- `migrations/**`, `src/storage/migrations/**`, acceptance models/services/routes, metrics repository/poller business logic, frontend components/helpers or handwritten types, deployment/SSH configuration, provider-generation clients, `.env*`, or key files. `web/src/types/api.generated.ts` is the sole generated frontend exception.

---

### Task 1: Shared Connector Error Vocabulary and Credential Truth

**Files:**

- Create: `tests/test_publish_connector_truth.py`
- Modify: `src/connectors/base.py`
- Modify: `src/connectors/registry.py`
- Modify: `src/connectors/tiktok_connector.py` (credential helpers only)
- Modify: `src/connectors/shopify_connector.py` (credential helpers only)
- Modify: `tests/test_publish_attempt_service.py` (readiness expectations only)

**Interfaces:**

- Produces `ConnectorCredentialState`, `ConnectorCredentialNotReady`, `ConnectorOutcomeAmbiguous`, and `ConnectorStatusUnavailable`.
- Produces `_credential_state()` and `_require_*()` per connector; registry and runtime execution must use the same validator.
- Keeps `PublishConnectorReadiness(platform, ready, reason)` shape unchanged while replacing mock vocabulary with `missing_credentials` / `invalid_configuration`.

- [x] **Step 1: Write RED credential/readiness tests**

Create `tests/test_publish_connector_truth.py` with this initial contract:

~~~python
from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import pytest

from src.connectors.base import (
    ConnectorCredentialNotReady,
    ConnectorOutcomeAmbiguous,
    ConnectorStatusUnavailable,
)


_CREDENTIAL_ENV = (
    "TIKTOK_ACCESS_TOKEN",
    "SHOPIFY_ACCESS_TOKEN",
    "SHOPIFY_API_KEY",
    "SHOPIFY_STORE_URL",
)


class ForbiddenAsyncClient:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("network client construction is forbidden")


def _clear_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _CREDENTIAL_ENV:
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("token", [None, "", "   ", "\t\n"])
def test_tiktok_readiness_rejects_missing_or_blank_token(
    token: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.connectors.registry import inspect_publish_readiness
    from src.connectors.tiktok_connector import _credential_state

    _clear_credentials(monkeypatch)
    if token is not None:
        monkeypatch.setenv("TIKTOK_ACCESS_TOKEN", token)

    state = _credential_state()
    readiness = inspect_publish_readiness("tiktok")

    assert state.ready is False
    assert state.reason == "missing_credentials"
    assert readiness.platform == "tiktok"
    assert readiness.ready is False
    assert readiness.reason == state.reason


def test_tiktok_readiness_accepts_trimmed_nonempty_fixture_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.connectors.registry import inspect_publish_readiness
    from src.connectors.tiktok_connector import _require_access_token

    _clear_credentials(monkeypatch)
    monkeypatch.setenv("TIKTOK_ACCESS_TOKEN", "  fixture-tiktok-token  ")

    assert _require_access_token() == "fixture-tiktok-token"
    assert inspect_publish_readiness("tiktok").ready is True


@pytest.mark.parametrize(
    ("access_token", "legacy_token", "store", "reason"),
    [
        (None, None, None, "missing_credentials"),
        ("", "", "fixture-store.myshopify.invalid", "missing_credentials"),
        ("   ", None, "fixture-store.myshopify.invalid", "missing_credentials"),
        ("fixture-token", None, None, "missing_credentials"),
        (None, "fixture-legacy", "", "missing_credentials"),
        ("fixture-token", None, "https://fixture.myshopify.invalid", "invalid_configuration"),
        ("fixture-token", None, "fixture.myshopify.invalid/path", "invalid_configuration"),
        ("fixture-token", None, "user@fixture.myshopify.invalid", "invalid_configuration"),
        ("fixture-token", None, "fixture.myshopify.invalid?x=1", "invalid_configuration"),
        ("fixture-token", None, "fixture.myshopify.invalid#x", "invalid_configuration"),
        ("fixture-token", None, " fixture.myshopify.invalid", "invalid_configuration"),
        ("fixture-token", None, "fixture_store.myshopify.invalid", "invalid_configuration"),
    ],
)
def test_shopify_readiness_rejects_partial_or_invalid_configuration(
    access_token: str | None,
    legacy_token: str | None,
    store: str | None,
    reason: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.connectors.registry import inspect_publish_readiness
    from src.connectors.shopify_connector import _credential_state

    _clear_credentials(monkeypatch)
    for name, value in (
        ("SHOPIFY_ACCESS_TOKEN", access_token),
        ("SHOPIFY_API_KEY", legacy_token),
        ("SHOPIFY_STORE_URL", store),
    ):
        if value is not None:
            monkeypatch.setenv(name, value)

    state = _credential_state()
    readiness = inspect_publish_readiness("shopify")

    assert state.ready is False
    assert state.reason == reason
    assert readiness.ready is False
    assert readiness.reason == reason


def test_shopify_canonical_token_precedes_legacy_and_legacy_remains_supported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.connectors.shopify_connector import _require_credentials

    _clear_credentials(monkeypatch)
    monkeypatch.setenv("SHOPIFY_ACCESS_TOKEN", " canonical-fixture ")
    monkeypatch.setenv("SHOPIFY_API_KEY", "legacy-fixture")
    monkeypatch.setenv("SHOPIFY_STORE_URL", "fixture-store.myshopify.invalid")
    assert _require_credentials() == (
        "canonical-fixture",
        "fixture-store.myshopify.invalid",
    )

    monkeypatch.delenv("SHOPIFY_ACCESS_TOKEN")
    assert _require_credentials() == (
        "legacy-fixture",
        "fixture-store.myshopify.invalid",
    )


@pytest.mark.parametrize("platform", ["tiktok", "shopify"])
def test_allow_mock_mode_never_changes_publish_readiness(
    platform: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.connectors.registry import inspect_publish_readiness

    _clear_credentials(monkeypatch)
    monkeypatch.setenv("ALLOW_MOCK_MODE", "1")
    first = inspect_publish_readiness(platform)
    monkeypatch.setenv("ALLOW_MOCK_MODE", "0")
    second = inspect_publish_readiness(platform)
    assert (first.ready, first.reason) == (False, "missing_credentials")
    assert (second.ready, second.reason) == (False, "missing_credentials")


def test_readiness_rejects_unsupported_platform_without_connector_construction() -> None:
    from src.connectors.registry import inspect_publish_readiness

    with pytest.raises(ValueError, match="Unsupported platform"):
        inspect_publish_readiness("instagram")
~~~

- [x] **Step 2: Run the Task 1 RED gate**

Run:

~~~bash
.venv/bin/python -m pytest tests/test_publish_connector_truth.py -k 'readiness or credential' -q
~~~

Expected: collection or assertions fail because the typed errors and `_credential_state` / `_require_*` interfaces do not exist, and readiness still uses `_is_mock_mode` plus `missing_credentials_or_mock_mode`.

- [x] **Step 3: Implement the typed base contract**

Replace `src/connectors/base.py` with:

~~~python
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Literal


ConnectorCredentialReason = Literal[
    "missing_credentials",
    "invalid_configuration",
]


@dataclass(frozen=True, slots=True)
class ConnectorCredentialState:
    ready: bool
    reason: ConnectorCredentialReason | None

    def __post_init__(self) -> None:
        if self.ready is (self.reason is not None):
            raise ValueError("connector credential state is inconsistent")


class ConnectorCredentialNotReady(RuntimeError):
    def __init__(self, reason: ConnectorCredentialReason) -> None:
        self.reason = reason
        super().__init__(reason)


class ConnectorOutcomeAmbiguous(RuntimeError):
    def __init__(self) -> None:
        super().__init__("connector_outcome_ambiguous")


class ConnectorStatusUnavailable(RuntimeError):
    def __init__(self) -> None:
        super().__init__("connector_status_unavailable")


class PlatformConnector(ABC):
    @abstractmethod
    async def publish(self, content: dict[str, Any]) -> dict[str, Any]:
        """Return a deterministic mapping with exact success/simulated truth."""
        raise NotImplementedError

    @abstractmethod
    async def get_status(self, post_id: str) -> dict[str, Any]:
        """Return a trusted real status mapping or raise a typed error."""
        raise NotImplementedError
~~~

- [x] **Step 4: Add the one-validator-per-platform credential helpers**

In `src/connectors/tiktok_connector.py`, replace `_is_mock_mode()` with:

~~~python
def _read_nonempty_env(name: str) -> str | None:
    raw = os.environ.get(name)
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    return value or None


def _credential_state() -> ConnectorCredentialState:
    ready = _read_nonempty_env("TIKTOK_ACCESS_TOKEN") is not None
    return ConnectorCredentialState(
        ready=ready,
        reason=None if ready else "missing_credentials",
    )


def _require_access_token() -> str:
    state = _credential_state()
    token = _read_nonempty_env("TIKTOK_ACCESS_TOKEN")
    if not state.ready or token is None:
        raise ConnectorCredentialNotReady(state.reason or "missing_credentials")
    return token
~~~

Update its base imports exactly to include `ConnectorCredentialNotReady` and `ConnectorCredentialState`; the publish/status methods will start calling `_require_access_token()` in Tasks 2 and 5.

In `src/connectors/shopify_connector.py`, add `re` and `urlsplit`, replace `_is_mock_mode()` with:

~~~python
_STORE_HOST_RE = re.compile(
    r"^(?=.{1,253}$)"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)"
    r"(?:\.(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?))*$"
)


def _read_nonempty_env(name: str) -> str | None:
    raw = os.environ.get(name)
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    return value or None


def _selected_token() -> str | None:
    return _read_nonempty_env("SHOPIFY_ACCESS_TOKEN") or _read_nonempty_env(
        "SHOPIFY_API_KEY"
    )


def _valid_store_host(value: str) -> bool:
    if not value or any(character.isspace() for character in value):
        return False
    try:
        parsed = urlsplit(f"//{value}")
        parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == ""
        and parsed.path == ""
        and parsed.query == ""
        and parsed.fragment == ""
        and parsed.username is None
        and parsed.password is None
        and parsed.port is None
        and parsed.hostname is not None
        and parsed.netloc == value
        and parsed.hostname.lower() == value.lower()
        and _STORE_HOST_RE.fullmatch(value) is not None
    )


def _credential_state() -> ConnectorCredentialState:
    token = _selected_token()
    store = os.environ.get("SHOPIFY_STORE_URL")
    if token is None or not isinstance(store, str) or not store:
        return ConnectorCredentialState(False, "missing_credentials")
    if not _valid_store_host(store):
        return ConnectorCredentialState(False, "invalid_configuration")
    return ConnectorCredentialState(True, None)


def _require_credentials() -> tuple[str, str]:
    state = _credential_state()
    token = _selected_token()
    store = os.environ.get("SHOPIFY_STORE_URL")
    if (
        not state.ready
        or token is None
        or not isinstance(store, str)
        or not _valid_store_host(store)
    ):
        raise ConnectorCredentialNotReady(state.reason or "invalid_configuration")
    return token, store
~~~

Update its base imports exactly to include `ConnectorCredentialNotReady` and `ConnectorCredentialState`. Do not yet change the publish/status flow in this task.

- [x] **Step 5: Replace registry mock readiness with strict credential readiness**

Replace `inspect_publish_readiness()` in `src/connectors/registry.py` with:

~~~python
def inspect_publish_readiness(platform: str) -> PublishConnectorReadiness:
    """Project strict credential readiness without network or connector creation."""

    if platform == "tiktok":
        from src.connectors.tiktok_connector import _credential_state

        selected_platform: Literal["tiktok", "shopify"] = "tiktok"
    elif platform == "shopify":
        from src.connectors.shopify_connector import _credential_state

        selected_platform = "shopify"
    else:
        raise ValueError(f"Unsupported platform: {platform}")
    state = _credential_state()
    return PublishConnectorReadiness(
        platform=selected_platform,
        ready=state.ready,
        reason=state.reason,
    )
~~~

Also change the `reason` field annotation to `ConnectorCredentialReason | None`, import that alias from `src.connectors.base`, and update the docstring so no mock-mode concept remains.

- [x] **Step 6: Migrate W1-23 readiness tests without changing orchestration behavior**

In `tests/test_publish_attempt_service.py`:

1. Change the harness false reason from `missing_credentials_or_mock_mode` to `missing_credentials`.
2. Replace `test_readiness_reports_mock_without_exposing_credentials` with a test that monkeypatches `_credential_state()` to `ConnectorCredentialState(False, "missing_credentials")` and asserts one call, no connector instantiation, frozen projection, and no token text.
3. Replace the two `_is_mock_mode` monkeypatches in `test_readiness_ready_is_no_network_and_calls_only_existing_predicate` with `_credential_state` returning `ConnectorCredentialState(True, None)`.

Use this exact replacement body for the first test:

~~~python
def test_readiness_reports_missing_credentials_without_exposing_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.connectors import registry
    from src.connectors.base import ConnectorCredentialState

    calls = 0

    def credential_state() -> ConnectorCredentialState:
        nonlocal calls
        calls += 1
        return ConnectorCredentialState(False, "missing_credentials")

    monkeypatch.setattr(
        "src.connectors.tiktok_connector._credential_state",
        credential_state,
    )
    monkeypatch.setattr(
        registry,
        "get_connector",
        lambda _: pytest.fail("readiness must not instantiate a connector"),
    )

    readiness = registry.inspect_publish_readiness("tiktok")

    assert calls == 1
    assert readiness.ready is False
    assert readiness.reason == "missing_credentials"
    assert readiness.platform == "tiktok"
    assert "token" not in repr(readiness).lower()
    with pytest.raises((AttributeError, TypeError)):
        readiness.ready = True
~~~

- [x] **Step 7: Run Task 1 GREEN and focused regression**

Run:

~~~bash
.venv/bin/python -m pytest tests/test_publish_connector_truth.py -k 'readiness or credential' tests/test_publish_attempt_service.py -k readiness -q
.venv/bin/python -m ruff check src/connectors/base.py src/connectors/registry.py src/connectors/tiktok_connector.py src/connectors/shopify_connector.py tests/test_publish_connector_truth.py tests/test_publish_attempt_service.py
git diff --check -- src/connectors/base.py src/connectors/registry.py src/connectors/tiktok_connector.py src/connectors/shopify_connector.py tests/test_publish_connector_truth.py tests/test_publish_attempt_service.py
~~~

Expected: all selected tests pass; no HTTP client is constructed; no business publish/status behavior is claimed complete yet.

---
### Task 2: TikTok Publish and Status Fail Closed

**Files:**

- Modify: `tests/test_publish_connector_truth.py`
- Modify: `src/connectors/tiktok_connector.py`
- Modify: `tests/test_connectors_mock.py`
- Modify: `tests/test_publish_connector_log_safety.py`

**Interfaces:**

- `TikTokConnector.publish()` raises `ConnectorCredentialNotReady` before file/client access when the token is unavailable.
- Deterministic public mappings always include `simulated: False`.
- A verified 4xx/API rejection returns deterministic `success=False`; 5xx, transport failure, JSON failure, or missing acknowledgement fields raise `ConnectorOutcomeAmbiguous`.
- `get_status()` returns a trusted real mapping with `simulated: False` or raises `ConnectorStatusUnavailable`; it never fabricates `published`.

- [x] **Step 1: Append TikTok RED tests**

Append to `tests/test_publish_connector_truth.py`:

~~~python
@pytest.mark.asyncio
async def test_tiktok_missing_credentials_block_publish_and_status_before_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.connectors.tiktok_connector as module
    from src.connectors.tiktok_connector import TikTokConnector

    _clear_credentials(monkeypatch)
    monkeypatch.setattr(module.httpx, "AsyncClient", ForbiddenAsyncClient)
    connector = TikTokConnector()

    with pytest.raises(ConnectorCredentialNotReady) as publish_error:
        await connector.publish({"video_path": "/not/read.mp4"})
    with pytest.raises(ConnectorCredentialNotReady) as status_error:
        await connector.get_status("post-fixture")

    assert publish_error.value.reason == "missing_credentials"
    assert status_error.value.reason == "missing_credentials"


@pytest.mark.asyncio
async def test_tiktok_missing_video_is_real_deterministic_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.connectors.tiktok_connector as module
    from src.connectors.tiktok_connector import TikTokConnector

    monkeypatch.setenv("TIKTOK_ACCESS_TOKEN", "fixture-token")
    monkeypatch.setattr(module.httpx, "AsyncClient", ForbiddenAsyncClient)

    result = await TikTokConnector().publish(
        {"video_path": str(tmp_path / "missing.mp4")}
    )

    assert result == {
        "success": False,
        "simulated": False,
        "error": "tiktok_video_unavailable",
        "status": "failed",
        "platform": "tiktok",
    }


@pytest.mark.asyncio
async def test_tiktok_publish_projects_only_exact_real_truth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.connectors.tiktok_connector import TikTokConnector

    monkeypatch.setenv("TIKTOK_ACCESS_TOKEN", "fixture-token")
    video = tmp_path / "fixture.mp4"
    video.write_bytes(b"fixture-video")
    connector = TikTokConnector()

    async def uploaded(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"success": True, "publish_id": "publish-fixture"}

    async def published(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "success": True,
            "post_id": "post-fixture",
            "url": "https://tiktok.invalid/post-fixture",
        }

    monkeypatch.setattr(connector, "_upload_video", uploaded)
    monkeypatch.setattr(connector, "_publish_video", published)

    result = await connector.publish(
        {"video_path": str(video), "description": "Reviewed"}
    )

    assert result["success"] is True
    assert result["simulated"] is False
    assert result["platform"] == "tiktok"
    assert result["post_id"] == "post-fixture"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "helper_result",
    [
        {},
        {"success": 1},
        {"success": True},
        {"success": True, "publish_id": ""},
    ],
)
async def test_tiktok_malformed_upload_acknowledgement_is_ambiguous(
    helper_result: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.connectors.tiktok_connector import TikTokConnector

    monkeypatch.setenv("TIKTOK_ACCESS_TOKEN", "fixture-token")
    video = tmp_path / "fixture.mp4"
    video.write_bytes(b"fixture-video")
    connector = TikTokConnector()

    async def malformed(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return helper_result

    monkeypatch.setattr(connector, "_upload_video", malformed)
    with pytest.raises(ConnectorOutcomeAmbiguous):
        await connector.publish({"video_path": str(video)})


def test_tiktok_runtime_source_has_no_publish_or_status_mock() -> None:
    import src.connectors.tiktok_connector as module

    source = inspect.getsource(module)
    for forbidden in (
        "_mock_publish",
        "_mock_status",
        "tt_mock_",
        "tiktok_mock_publish",
    ):
        assert forbidden not in source
~~~

- [x] **Step 2: Run the TikTok RED gate**

Run:

~~~bash
.venv/bin/python -m pytest tests/test_publish_connector_truth.py -k tiktok -q
~~~

Expected: missing-credential calls still return mock values, deterministic mappings lack `simulated`, malformed acknowledgements are collapsed, and source guards find runtime mock helpers.

- [x] **Step 3: Replace TikTok runtime publish/status behavior**

Remove `asyncio` and `uuid4` imports, add `_MISSING = object()`, and import `ConnectorOutcomeAmbiguous` plus `ConnectorStatusUnavailable` from `src.connectors.base`.

Add this method to `TikTokConnector` and use it for publish/status calls so injected clients remain available to tests:

~~~python
    async def _post(
        self,
        url: str,
        *,
        timeout_seconds: float,
        **kwargs: Any,
    ) -> httpx.Response:
        if self._http_client is not None:
            return await self._http_client.post(url, **kwargs)
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            return await client.post(url, **kwargs)
~~~

Replace `publish()` completely with:

~~~python
    async def publish(self, content: dict[str, Any]) -> dict[str, Any]:
        token = _require_access_token()
        video_path = content.get("video_path")
        description = content.get("description", content.get("title", ""))
        if not isinstance(video_path, str) or not video_path or not os.path.isfile(video_path):
            logger.warning("tiktok_video_unavailable")
            return {
                "success": False,
                "simulated": False,
                "error": "tiktok_video_unavailable",
                "status": "failed",
                "platform": "tiktok",
            }
        if not isinstance(description, str):
            description = ""

        try:
            upload_result = await self._upload_video(token, video_path)
            upload_success = upload_result.get("success", _MISSING)
            if type(upload_success) is not bool:
                raise ConnectorOutcomeAmbiguous
            if upload_success is False:
                return {
                    "success": False,
                    "simulated": False,
                    "error": "tiktok_upload_failed",
                    "status": "failed",
                    "platform": "tiktok",
                }
            publish_id = upload_result.get("publish_id")
            if not isinstance(publish_id, str) or not publish_id:
                raise ConnectorOutcomeAmbiguous

            publish_result = await self._publish_video(
                token,
                publish_id,
                description,
            )
            publish_success = publish_result.get("success", _MISSING)
            if type(publish_success) is not bool:
                raise ConnectorOutcomeAmbiguous
            if publish_success is False:
                return {
                    "success": False,
                    "simulated": False,
                    "error": "tiktok_publish_failed",
                    "status": "failed",
                    "platform": "tiktok",
                }
            post_id = publish_result.get("post_id")
            if not isinstance(post_id, str) or not post_id:
                raise ConnectorOutcomeAmbiguous
            post_url = publish_result.get("url")
            if post_url is None:
                username = os.environ.get("TIKTOK_USERNAME", "user")
                post_url = f"https://tiktok.com/@{username}/video/{post_id}"
            if not isinstance(post_url, str) or not post_url:
                raise ConnectorOutcomeAmbiguous
            return {
                "success": True,
                "simulated": False,
                "post_id": post_id,
                "url": post_url,
                "status": "published",
                "platform": "tiktok",
                "published_at": datetime.now().isoformat(),
            }
        except ConnectorOutcomeAmbiguous:
            raise
        except Exception as exc:
            logger.error(
                "tiktok_publish_outcome_ambiguous error_class=%s",
                type(exc).__name__,
            )
            raise ConnectorOutcomeAmbiguous from None
~~~

Use `raise ConnectorOutcomeAmbiguous()` rather than the class object if the active Python/Ruff version rejects class raising during implementation.

Replace `_upload_video()` with:

~~~python
    async def _upload_video(
        self,
        token: str,
        video_path: str,
    ) -> dict[str, Any]:
        try:
            with open(video_path, "rb") as video_file:
                response = await self._post(
                    _TIKTOK_UPLOAD_URL,
                    timeout_seconds=300.0,
                    headers={"Authorization": f"Bearer {token}"},
                    files={
                        "video": (
                            os.path.basename(video_path),
                            video_file,
                            "video/mp4",
                        )
                    },
                )
        except OSError as exc:
            logger.error("tiktok_upload_failed error_class=%s", type(exc).__name__)
            return {"success": False, "error": "tiktok_upload_failed"}
        except Exception as exc:
            logger.error(
                "tiktok_upload_outcome_ambiguous error_class=%s",
                type(exc).__name__,
            )
            raise ConnectorOutcomeAmbiguous from None

        if 400 <= response.status_code < 500:
            logger.error("tiktok_upload_failed http_status=%s", response.status_code)
            return {"success": False, "error": "tiktok_upload_failed"}
        if response.status_code != 200:
            logger.error(
                "tiktok_upload_outcome_ambiguous http_status=%s",
                response.status_code,
            )
            raise ConnectorOutcomeAmbiguous
        try:
            payload = response.json()
            data = payload.get("data") if isinstance(payload, dict) else None
        except Exception as exc:
            logger.error(
                "tiktok_upload_outcome_ambiguous error_class=%s",
                type(exc).__name__,
            )
            raise ConnectorOutcomeAmbiguous from None
        if not isinstance(data, dict) or "error_code" not in data:
            raise ConnectorOutcomeAmbiguous
        if data["error_code"] not in (0, "0"):
            logger.error("tiktok_upload_failed")
            return {"success": False, "error": "tiktok_upload_failed"}
        publish_id = data.get("publish_id")
        if not isinstance(publish_id, str) or not publish_id:
            raise ConnectorOutcomeAmbiguous
        return {"success": True, "publish_id": publish_id}
~~~

Replace `_publish_video()` with:

~~~python
    async def _publish_video(
        self,
        token: str,
        publish_id: str,
        description: str,
    ) -> dict[str, Any]:
        try:
            response = await self._post(
                _TIKTOK_PUBLISH_URL,
                timeout_seconds=60.0,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={"publish_id": publish_id, "description": description},
            )
        except Exception as exc:
            logger.error(
                "tiktok_publish_outcome_ambiguous error_class=%s",
                type(exc).__name__,
            )
            raise ConnectorOutcomeAmbiguous from None
        if 400 <= response.status_code < 500:
            logger.error("tiktok_publish_failed http_status=%s", response.status_code)
            return {"success": False, "error": "tiktok_publish_failed"}
        if response.status_code != 200:
            logger.error(
                "tiktok_publish_outcome_ambiguous http_status=%s",
                response.status_code,
            )
            raise ConnectorOutcomeAmbiguous
        try:
            payload = response.json()
            data = payload.get("data") if isinstance(payload, dict) else None
        except Exception as exc:
            logger.error(
                "tiktok_publish_outcome_ambiguous error_class=%s",
                type(exc).__name__,
            )
            raise ConnectorOutcomeAmbiguous from None
        if not isinstance(data, dict) or "error_code" not in data:
            raise ConnectorOutcomeAmbiguous
        if data["error_code"] not in (0, "0"):
            logger.error("tiktok_publish_failed")
            return {"success": False, "error": "tiktok_publish_failed"}
        post_id = data.get("post_id", publish_id)
        if not isinstance(post_id, str) or not post_id:
            raise ConnectorOutcomeAmbiguous
        username = os.environ.get("TIKTOK_USERNAME", "user")
        return {
            "success": True,
            "post_id": post_id,
            "url": f"https://tiktok.com/@{username}/video/{post_id}",
        }
~~~

Replace `get_status()` with:

~~~python
    async def get_status(self, post_id: str) -> dict[str, Any]:
        token = _require_access_token()
        try:
            response = await self._post(
                _TIKTOK_QUERY_URL,
                timeout_seconds=30.0,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={"post_id": post_id},
            )
            if response.status_code != 200:
                raise ConnectorStatusUnavailable
            payload = response.json()
            data = payload.get("data") if isinstance(payload, dict) else None
            if (
                not isinstance(data, dict)
                or data.get("error_code") not in (0, "0")
                or not isinstance(data.get("video"), dict)
            ):
                raise ConnectorStatusUnavailable
            video = data["video"]
            status = video.get("status")
            if not isinstance(status, str) or not status.strip():
                raise ConnectorStatusUnavailable
            return {
                "post_id": post_id,
                "status": status,
                "views": video.get("view_count", 0),
                "likes": video.get("like_count", 0),
                "comments": video.get("comment_count", 0),
                "shares": video.get("share_count", 0),
                "simulated": False,
            }
        except ConnectorStatusUnavailable:
            raise
        except Exception as exc:
            logger.error(
                "tiktok_status_unavailable error_class=%s",
                type(exc).__name__,
            )
            raise ConnectorStatusUnavailable from None
~~~

Delete `_mock_publish()` and `_mock_status()` entirely.

- [x] **Step 4: Replace obsolete mock compatibility tests**

In `tests/test_connectors_mock.py`, replace both `*_publish_mock_mode_returns_stub` tests with missing-credential `ConnectorCredentialNotReady` assertions, call `monkeypatch.delenv("TIKTOK_ACCESS_TOKEN", raising=False)` or the three exact Shopify credential names, and remove assertions for generated post IDs. For the four no-video/empty-content tests, configure fixture credentials and assert exact deterministic failure with `simulated is False`.

The TikTok no-credential replacement is:

~~~python
@pytest.mark.asyncio
async def test_tiktok_publish_without_credentials_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.connectors.base import ConnectorCredentialNotReady

    monkeypatch.delenv("TIKTOK_ACCESS_TOKEN", raising=False)
    with pytest.raises(ConnectorCredentialNotReady):
        await TikTokConnector().publish(
            {"title": "Test Video", "video_path": "/tmp/test.mp4"}
        )
~~~

- [x] **Step 5: Migrate TikTok log-safety expectations**

In `tests/test_publish_connector_log_safety.py` make these exact semantic changes:

- Add `"simulated": False` to both public missing-video expected mappings.
- In `test_outer_publish_exception_is_stable_and_message_free`, expect `ConnectorOutcomeAmbiguous`, build evidence from `caplog.text + repr(error.value)`, and retain the sentinel/path/credential absence checks.
- In public upload/publish failure projections, assert `result["simulated"] is False`.
- In `test_tiktok_http_and_remote_failures_are_body_and_message_free`, keep the 200 remote error as deterministic `{"success": False, "error": expected}`; expect `ConnectorOutcomeAmbiguous` for 503 and JSON exceptions. In every branch assert one client call and no raw body, token, or absolute path in log/exception evidence.
- Keep the success call order unchanged and add `assert tiktok_result["simulated"] is False`.

- [x] **Step 6: Run Task 2 GREEN and connector regression**

Run:

~~~bash
.venv/bin/python -m pytest tests/test_publish_connector_truth.py -k tiktok tests/test_connectors_mock.py -k tiktok tests/test_publish_connector_log_safety.py -k tiktok -q
.venv/bin/python -m ruff check src/connectors/tiktok_connector.py tests/test_publish_connector_truth.py tests/test_connectors_mock.py tests/test_publish_connector_log_safety.py
git diff --check -- src/connectors/tiktok_connector.py tests/test_publish_connector_truth.py tests/test_connectors_mock.py tests/test_publish_connector_log_safety.py
~~~

Expected: TikTok focused tests pass with zero real network; missing credential never reads the video or builds a client; deterministic and ambiguous outcomes remain distinct.

---

### Task 3: Shopify Publish and Status Fail Closed

**Files:**

- Modify: `tests/test_publish_connector_truth.py`
- Modify: `src/connectors/shopify_connector.py`
- Modify: `tests/test_connectors_mock.py`
- Modify: `tests/test_publish_connector_log_safety.py`
- Verify only: `tests/test_metrics_poller.py`

**Interfaces:**

- `ShopifyConnector.publish()` rechecks canonical/legacy token plus strict store host before file/client access.
- `_headers(token)` and `_admin_url(store)` require validated arguments; neither has a mock or unauthenticated fallback.
- Verified 4xx and mutation `userErrors` are deterministic failure; top-level GraphQL `errors`, 5xx, transport, JSON, or missing acknowledgement shape are ambiguous.
- Optional product association remains ancillary: its failure is logged safely and does not replace a trusted successful file creation.
- `get_status()` returns trusted real `fileStatus` with `simulated=False` or raises `ConnectorStatusUnavailable`.

- [x] **Step 1: Append Shopify and direct-status RED tests**

Append to `tests/test_publish_connector_truth.py`:

~~~python
class FakeResponse:
    def __init__(
        self,
        status_code: int,
        payload: Any,
        *,
        error: Exception | None = None,
    ) -> None:
        self.status_code = status_code
        self.payload = payload
        self.error = error

    def json(self) -> Any:
        if self.error is not None:
            raise self.error
        return self.payload


class OneResponseClient:
    def __init__(
        self,
        response: FakeResponse | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, Any]] = []

    async def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "store",
    [None, "", "https://fixture.myshopify.invalid", "fixture.myshopify.invalid/path"],
)
async def test_shopify_invalid_credentials_block_publish_and_status_before_network(
    store: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.connectors.shopify_connector as module
    from src.connectors.shopify_connector import ShopifyConnector

    _clear_credentials(monkeypatch)
    monkeypatch.setenv("SHOPIFY_ACCESS_TOKEN", "fixture-token")
    if store is not None:
        monkeypatch.setenv("SHOPIFY_STORE_URL", store)
    monkeypatch.setattr(module.httpx, "AsyncClient", ForbiddenAsyncClient)
    connector = ShopifyConnector()

    with pytest.raises(ConnectorCredentialNotReady):
        await connector.publish({"video_path": "/not/read.mp4"})
    with pytest.raises(ConnectorCredentialNotReady):
        await connector.get_status("gid://shopify/MediaFile/fixture")


@pytest.mark.asyncio
async def test_shopify_missing_video_is_real_deterministic_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.connectors.shopify_connector as module
    from src.connectors.shopify_connector import ShopifyConnector

    monkeypatch.setenv("SHOPIFY_ACCESS_TOKEN", "fixture-token")
    monkeypatch.setenv("SHOPIFY_STORE_URL", "fixture.myshopify.invalid")
    monkeypatch.setattr(module.httpx, "AsyncClient", ForbiddenAsyncClient)

    result = await ShopifyConnector().publish(
        {"video_path": str(tmp_path / "missing.mp4")}
    )

    assert result == {
        "success": False,
        "simulated": False,
        "error": "shopify_video_unavailable",
        "status": "failed",
        "platform": "shopify",
    }


@pytest.mark.asyncio
async def test_shopify_publish_projects_only_exact_real_truth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.connectors.shopify_connector import ShopifyConnector

    monkeypatch.setenv("SHOPIFY_ACCESS_TOKEN", "fixture-token")
    monkeypatch.setenv("SHOPIFY_STORE_URL", "fixture.myshopify.invalid")
    video = tmp_path / "fixture.mp4"
    video.write_bytes(b"fixture-video")
    connector = ShopifyConnector()

    async def uploaded(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"success": True, "media_id": "gid://shopify/MediaFile/fixture"}

    monkeypatch.setattr(connector, "_upload_video", uploaded)
    result = await connector.publish(
        {"video_path": str(video), "title": "Reviewed", "product_name": ""}
    )

    assert result["success"] is True
    assert result["simulated"] is False
    assert result["platform"] == "shopify"
    assert result["post_id"] == "gid://shopify/MediaFile/fixture"
    assert "mock-store" not in result["url"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("platform", "payload", "expected_status"),
    [
        (
            "tiktok",
            {
                "data": {
                    "error_code": 0,
                    "video": {"status": "unknown", "view_count": 0},
                }
            },
            "unknown",
        ),
        (
            "shopify",
            {
                "data": {
                    "node": {
                        "id": "gid://shopify/MediaFile/fixture",
                        "fileStatus": "PROCESSING",
                        "preview": None,
                    }
                }
            },
            "PROCESSING",
        ),
    ],
)
async def test_direct_status_accepts_only_trusted_real_nonterminal_state(
    platform: str,
    payload: dict[str, Any],
    expected_status: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_credentials(monkeypatch)
    client = OneResponseClient(FakeResponse(200, payload))
    if platform == "tiktok":
        from src.connectors.tiktok_connector import TikTokConnector

        monkeypatch.setenv("TIKTOK_ACCESS_TOKEN", "fixture-token")
        connector = TikTokConnector(http_client=client)  # type: ignore[arg-type]
        post_id = "post-fixture"
    else:
        from src.connectors.shopify_connector import ShopifyConnector

        monkeypatch.setenv("SHOPIFY_ACCESS_TOKEN", "fixture-token")
        monkeypatch.setenv("SHOPIFY_STORE_URL", "fixture.myshopify.invalid")
        connector = ShopifyConnector(http_client=client)  # type: ignore[arg-type]
        post_id = "gid://shopify/MediaFile/fixture"

    result = await connector.get_status(post_id)

    assert result["post_id"] == post_id
    assert result["status"] == expected_status
    assert result["simulated"] is False
    assert len(client.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("platform", ["tiktok", "shopify"])
@pytest.mark.parametrize("failure_kind", ["http", "json", "timeout"])
async def test_direct_status_failure_is_typed_and_message_free(
    platform: str,
    failure_kind: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_credentials(monkeypatch)
    if failure_kind == "http":
        client = OneResponseClient(FakeResponse(503, {}))
    elif failure_kind == "json":
        client = OneResponseClient(
            FakeResponse(200, {}, error=ValueError("raw-body"))
        )
    else:
        client = OneResponseClient(error=TimeoutError("raw-timeout"))
    if platform == "tiktok":
        from src.connectors.tiktok_connector import TikTokConnector

        monkeypatch.setenv("TIKTOK_ACCESS_TOKEN", "fixture-token")
        connector = TikTokConnector(http_client=client)  # type: ignore[arg-type]
    else:
        from src.connectors.shopify_connector import ShopifyConnector

        monkeypatch.setenv("SHOPIFY_ACCESS_TOKEN", "fixture-token")
        monkeypatch.setenv("SHOPIFY_STORE_URL", "fixture.myshopify.invalid")
        connector = ShopifyConnector(http_client=client)  # type: ignore[arg-type]

    with pytest.raises(ConnectorStatusUnavailable) as error:
        await connector.get_status("post-fixture")
    assert "raw-" not in repr(error.value)


def test_shopify_runtime_source_has_no_publish_or_status_mock() -> None:
    import src.connectors.shopify_connector as module

    source = inspect.getsource(module)
    for forbidden in (
        "_mock_publish",
        "_mock_status",
        "sp_mock_",
        "shopify_mock_publish",
        "mock-store.myshopify.com",
    ):
        assert forbidden not in source
~~~

- [x] **Step 2: Run the Shopify/status RED gate**

Run:

~~~bash
.venv/bin/python -m pytest tests/test_publish_connector_truth.py -k 'shopify or direct_status' -q
~~~

Expected: Shopify still mock-publishes/statuses, accepts invalid store strings, lacks `simulated`, and uses mock/unauthenticated admin fallbacks.

- [x] **Step 3: Make Shopify URL/header construction require validated inputs**

Replace `_admin_url()` and `_headers()` with:

~~~python
def _admin_url(store: str) -> str:
    return f"https://{store}/admin"


def _headers(token: str) -> dict[str, str]:
    return {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json",
    }
~~~

In `fetch_metrics()`, change only the call to:

~~~python
        response = await self._post_shopifyql_query(store_url, token, query)
~~~

Replace `_post_shopifyql_query()` with the same query body and this exact signature/request plumbing:

~~~python
    async def _post_shopifyql_query(
        self,
        store_url: str,
        token: str,
        shopifyql: str,
    ) -> httpx.Response:
        graphql_url = _SHOPIFY_GRAPHQL_URL.format(store=store_url)
        graphql_query = """
        query ShopifyMetrics($query: String!) {
            shopifyqlQuery(query: $query) {
                tableData {
                    columns {
                        name
                        dataType
                        displayName
                    }
                    rows
                }
                parseErrors
            }
        }
        """
        payload = {"query": graphql_query, "variables": {"query": shopifyql}}
        if self._http_client is not None:
            return await self._http_client.post(
                graphql_url,
                headers=_headers(token),
                json=payload,
            )
        async with httpx.AsyncClient(timeout=30.0) as client:
            return await client.post(
                graphql_url,
                headers=_headers(token),
                json=payload,
            )
~~~

This is plumbing only; do not change metrics classification or response normalization.

- [x] **Step 4: Add strict Shopify HTTP/GraphQL projection helpers**

Import `ConnectorOutcomeAmbiguous` and `ConnectorStatusUnavailable`, add `_MISSING = object()`, and add:

~~~python
def _http_is_deterministic_rejection(response: httpx.Response) -> bool:
    return 400 <= response.status_code < 500


def _graphql_mutation(
    response: httpx.Response,
    field: str,
) -> tuple[dict[str, Any] | None, bool]:
    try:
        payload = response.json()
    except Exception:
        raise ConnectorOutcomeAmbiguous from None
    if not isinstance(payload, dict):
        raise ConnectorOutcomeAmbiguous
    if payload.get("errors"):
        raise ConnectorOutcomeAmbiguous
    data = payload.get("data")
    mutation = data.get(field) if isinstance(data, dict) else None
    if not isinstance(mutation, dict):
        raise ConnectorOutcomeAmbiguous
    user_errors = mutation.get("userErrors", _MISSING)
    if not isinstance(user_errors, list):
        raise ConnectorOutcomeAmbiguous
    if user_errors:
        return None, False
    return mutation, True
~~~

Add to `ShopifyConnector`:

~~~python
    async def _post(
        self,
        url: str,
        *,
        timeout_seconds: float,
        **kwargs: Any,
    ) -> httpx.Response:
        if self._http_client is not None:
            return await self._http_client.post(url, **kwargs)
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            return await client.post(url, **kwargs)
~~~

- [x] **Step 5: Replace Shopify public publish projection**

Replace `publish()` with:

~~~python
    async def publish(self, content: dict[str, Any]) -> dict[str, Any]:
        token, store_url = _require_credentials()
        video_path = content.get("video_path")
        title = content.get("title", "AI-generated video")
        product_name = content.get("product_name", "")
        if not isinstance(video_path, str) or not video_path or not os.path.isfile(video_path):
            logger.warning("shopify_video_unavailable")
            return {
                "success": False,
                "simulated": False,
                "error": "shopify_video_unavailable",
                "status": "failed",
                "platform": "shopify",
            }
        if not isinstance(title, str):
            title = "AI-generated video"
        if not isinstance(product_name, str):
            product_name = ""

        try:
            file_result = await self._upload_video(
                store_url,
                token,
                video_path,
                title,
            )
            upload_success = file_result.get("success", _MISSING)
            if type(upload_success) is not bool:
                raise ConnectorOutcomeAmbiguous
            if upload_success is False:
                return {
                    "success": False,
                    "simulated": False,
                    "error": "shopify_upload_failed",
                    "status": "failed",
                    "platform": "shopify",
                }
            media_id = file_result.get("media_id")
            if not isinstance(media_id, str) or not media_id:
                raise ConnectorOutcomeAmbiguous

            post_url = f"{_admin_url(store_url)}/products"
            if product_name:
                product_result = await self._associate_with_product(
                    store_url,
                    token,
                    media_id,
                    product_name,
                )
                if product_result.get("success") is True:
                    product_id = product_result.get("product_id")
                    if isinstance(product_id, str) and product_id:
                        post_url = f"{_admin_url(store_url)}/products/{product_id}"
                else:
                    logger.warning("shopify_association_failed")
            return {
                "success": True,
                "simulated": False,
                "post_id": media_id,
                "url": post_url,
                "status": "published",
                "platform": "shopify",
                "published_at": datetime.now().isoformat(),
            }
        except ConnectorOutcomeAmbiguous:
            raise
        except Exception as exc:
            logger.error(
                "shopify_publish_outcome_ambiguous error_class=%s",
                type(exc).__name__,
            )
            raise ConnectorOutcomeAmbiguous from None
~~~

- [x] **Step 6: Harden the three-stage upload without changing request order**

Replace `_upload_video()` completely with:

~~~python
    async def _upload_video(
        self,
        store_url: str,
        token: str,
        video_path: str,
        title: str,
    ) -> dict[str, Any]:
        graphql_url = _SHOPIFY_GRAPHQL_URL.format(store=store_url)
        headers = _headers(token)
        staging_mutation = """
        mutation StagedUploadsCreate($input: [StagedUploadInput!]!) {
            stagedUploadsCreate(input: $input) {
                stagedTargets {
                    url
                    resourceUrl
                    parameters {
                        name
                        value
                    }
                }
                userErrors {
                    field
                    message
                }
            }
        }
        """
        try:
            file_size = os.path.getsize(video_path)
            with open(video_path, "rb") as probe:
                probe.read(0)
        except OSError as exc:
            logger.error(
                "shopify_upload_failed error_class=%s",
                type(exc).__name__,
            )
            return {"success": False, "error": "shopify_upload_failed"}

        filename = os.path.basename(video_path)
        staging_variables = {
            "input": [
                {
                    "resource": "FILE",
                    "filename": filename,
                    "mimeType": "video/mp4",
                    "fileSize": str(file_size),
                }
            ]
        }
        try:
            staging_response = await self._post(
                graphql_url,
                timeout_seconds=60.0,
                headers=headers,
                json={
                    "query": staging_mutation,
                    "variables": staging_variables,
                },
            )
            if _http_is_deterministic_rejection(staging_response):
                logger.error(
                    "shopify_upload_failed http_status=%s",
                    staging_response.status_code,
                )
                return {"success": False, "error": "shopify_upload_failed"}
            if staging_response.status_code != 200:
                raise ConnectorOutcomeAmbiguous
            staging, staging_accepted = _graphql_mutation(
                staging_response,
                "stagedUploadsCreate",
            )
            if not staging_accepted:
                logger.error("shopify_upload_failed")
                return {"success": False, "error": "shopify_upload_failed"}
            assert staging is not None
            targets = staging.get("stagedTargets")
            if not isinstance(targets, list) or not targets:
                raise ConnectorOutcomeAmbiguous
            target = targets[0]
            if not isinstance(target, dict):
                raise ConnectorOutcomeAmbiguous
            upload_url = target.get("url")
            resource_url = target.get("resourceUrl")
            parameters = target.get("parameters")
            if (
                not isinstance(upload_url, str)
                or not upload_url
                or not isinstance(resource_url, str)
                or not resource_url
                or not isinstance(parameters, list)
            ):
                raise ConnectorOutcomeAmbiguous
            files: dict[str, tuple[str, Any, str]] = {}
            for parameter in parameters:
                if not isinstance(parameter, dict):
                    raise ConnectorOutcomeAmbiguous
                name = parameter.get("name")
                value = parameter.get("value")
                if not isinstance(name, str) or not isinstance(value, str):
                    raise ConnectorOutcomeAmbiguous
                files[name] = ("blob", value.encode(), "text/plain")
            with open(video_path, "rb") as video_file:
                files["file"] = (filename, video_file, "video/mp4")
                upload_response = await self._post(
                    upload_url,
                    timeout_seconds=300.0,
                    files=files,
                )
            if _http_is_deterministic_rejection(upload_response):
                logger.error(
                    "shopify_upload_failed http_status=%s",
                    upload_response.status_code,
                )
                return {"success": False, "error": "shopify_upload_failed"}
            if upload_response.status_code not in (200, 201):
                raise ConnectorOutcomeAmbiguous

            create_mutation = """
            mutation fileCreate($files: [FileCreateInput!]!) {
                fileCreate(files: $files) {
                    files {
                        id
                        alt
                        createdAt
                        fileStatus
                        ... on MediaFile {
                            preview {
                                url
                            }
                        }
                    }
                    userErrors {
                        field
                        message
                    }
                }
            }
            """
            create_response = await self._post(
                graphql_url,
                timeout_seconds=60.0,
                headers=headers,
                json={
                    "query": create_mutation,
                    "variables": {
                        "files": [
                            {
                                "alt": title,
                                "contentType": "VIDEO",
                                "originalSource": resource_url,
                            }
                        ]
                    },
                },
            )
            if _http_is_deterministic_rejection(create_response):
                logger.error(
                    "shopify_upload_failed http_status=%s",
                    create_response.status_code,
                )
                return {"success": False, "error": "shopify_upload_failed"}
            if create_response.status_code != 200:
                raise ConnectorOutcomeAmbiguous
            creation, creation_accepted = _graphql_mutation(
                create_response,
                "fileCreate",
            )
            if not creation_accepted:
                logger.error("shopify_upload_failed")
                return {"success": False, "error": "shopify_upload_failed"}
            assert creation is not None
            created_files = creation.get("files")
            if not isinstance(created_files, list) or not created_files:
                raise ConnectorOutcomeAmbiguous
            first_file = created_files[0]
            media_id = (
                first_file.get("id") if isinstance(first_file, dict) else None
            )
            if not isinstance(media_id, str) or not media_id:
                raise ConnectorOutcomeAmbiguous
            return {"success": True, "media_id": media_id}
        except ConnectorOutcomeAmbiguous:
            raise
        except Exception as exc:
            logger.error(
                "shopify_upload_outcome_ambiguous error_class=%s",
                type(exc).__name__,
            )
            raise ConnectorOutcomeAmbiguous from None
~~~

Do not add retry around any of the three requests.

- [x] **Step 7: Plumb validated token into optional association**

Make these exact diffs in `_associate_with_product()` without changing its ancillary result semantics:

~~~diff
-    async def _associate_with_product(
-        self, store_url: str, media_id: str, product_name: str
+    async def _associate_with_product(
+        self,
+        store_url: str,
+        token: str,
+        media_id: str,
+        product_name: str,
     ) -> dict[str, Any]:
@@
-        headers = _headers()
+        headers = _headers(token)
~~~

Keep its existing safe class-only catch and stable `shopify_association_failed` result because association is not the authoritative file-create receipt in W1-24.

- [x] **Step 8: Replace Shopify status behavior**

Replace `get_status()` with:

~~~python
    async def get_status(self, post_id: str) -> dict[str, Any]:
        token, store_url = _require_credentials()
        query = """
        query mediaStatus($id: ID!) {
            node(id: $id) {
                ... on MediaFile {
                    id
                    fileStatus
                    preview {
                        url
                    }
                }
            }
        }
        """
        try:
            response = await self._post(
                _SHOPIFY_GRAPHQL_URL.format(store=store_url),
                timeout_seconds=30.0,
                headers=_headers(token),
                json={"query": query, "variables": {"id": post_id}},
            )
            if response.status_code != 200:
                raise ConnectorStatusUnavailable
            payload = response.json()
            if not isinstance(payload, dict) or payload.get("errors"):
                raise ConnectorStatusUnavailable
            data = payload.get("data")
            node = data.get("node") if isinstance(data, dict) else None
            if not isinstance(node, dict):
                raise ConnectorStatusUnavailable
            node_id = node.get("id")
            status = node.get("fileStatus")
            if node_id != post_id or not isinstance(status, str) or not status.strip():
                raise ConnectorStatusUnavailable
            preview = node.get("preview")
            preview_url = preview.get("url", "") if isinstance(preview, dict) else ""
            return {
                "post_id": post_id,
                "status": status,
                "preview_url": preview_url,
                "simulated": False,
            }
        except ConnectorStatusUnavailable:
            raise
        except Exception as exc:
            logger.error(
                "shopify_status_unavailable error_class=%s",
                type(exc).__name__,
            )
            raise ConnectorStatusUnavailable from None
~~~

Delete `_mock_publish()` and `_mock_status()`, plus now-unused `asyncio` and `uuid4` imports.

- [x] **Step 9: Migrate Shopify mock/log-safety tests**

Replace `tests/test_connectors_mock.py` completely with the final fail-closed compatibility file:

~~~python
"""Credential-absence and invalid-content compatibility for publish connectors."""

from __future__ import annotations

import pytest

from src.connectors.base import ConnectorCredentialNotReady
from src.connectors.shopify_connector import ShopifyConnector
from src.connectors.tiktok_connector import TikTokConnector


@pytest.mark.asyncio
async def test_tiktok_publish_without_credentials_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TIKTOK_ACCESS_TOKEN", raising=False)
    with pytest.raises(ConnectorCredentialNotReady):
        await TikTokConnector().publish(
            {"title": "Test Video", "video_path": "/not/read.mp4"}
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("content", [{"title": "No Video"}, {}])
async def test_tiktok_invalid_content_is_real_deterministic_failure(
    content: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TIKTOK_ACCESS_TOKEN", "fixture-tiktok-token")
    result = await TikTokConnector().publish(content)
    assert result == {
        "success": False,
        "simulated": False,
        "error": "tiktok_video_unavailable",
        "status": "failed",
        "platform": "tiktok",
    }


@pytest.mark.asyncio
async def test_shopify_publish_without_credentials_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "SHOPIFY_ACCESS_TOKEN",
        "SHOPIFY_API_KEY",
        "SHOPIFY_STORE_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ConnectorCredentialNotReady):
        await ShopifyConnector().publish(
            {"title": "Test Product Video", "video_path": "/not/read.mp4"}
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    [
        {"title": "No Product", "video_path": ""},
        {},
    ],
)
async def test_shopify_invalid_content_is_real_deterministic_failure(
    content: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SHOPIFY_ACCESS_TOKEN", "fixture-shopify-token")
    monkeypatch.delenv("SHOPIFY_API_KEY", raising=False)
    monkeypatch.setenv("SHOPIFY_STORE_URL", "fixture.myshopify.invalid")
    result = await ShopifyConnector().publish(content)
    assert result == {
        "success": False,
        "simulated": False,
        "error": "shopify_video_unavailable",
        "status": "failed",
        "platform": "shopify",
    }
~~~

In `tests/test_publish_connector_log_safety.py`:

- Add `simulated=False` to public Shopify mappings.
- Pass `fixture-shopify-credential` to `_upload_video()` and `_associate_with_product()` after `store_url`.
- Split `test_shopify_upload_failures_return_only_stable_code` cases into deterministic mutation-`userErrors`/4xx cases and ambiguous top-level GraphQL-error/5xx/JSON/missing-shape cases. Deterministic cases retain the exact stable failure mapping; ambiguous cases expect `ConnectorOutcomeAmbiguous`.
- Keep exactly three upload calls and two association calls in the success cases.
- Keep ancillary association failure as public publish success, add `assert result["simulated"] is False`, and retain all raw-body/product/path absence assertions.

- [x] **Step 10: Run Task 3 GREEN and metrics regression**

Run:

~~~bash
.venv/bin/python -m pytest tests/test_publish_connector_truth.py -k 'shopify or direct_status' tests/test_connectors_mock.py -k shopify tests/test_publish_connector_log_safety.py -k shopify tests/test_metrics_poller.py -q
.venv/bin/python -m ruff check src/connectors/shopify_connector.py tests/test_publish_connector_truth.py tests/test_connectors_mock.py tests/test_publish_connector_log_safety.py tests/test_metrics_poller.py
git diff --check -- src/connectors/shopify_connector.py tests/test_publish_connector_truth.py tests/test_connectors_mock.py tests/test_publish_connector_log_safety.py tests/test_metrics_poller.py
~~~

Expected: Shopify/status focused tests and unchanged metrics regression pass with fake transports only; no mock receipt or status remains.

---

### Task 4: Publish Attempt Simulated Truth and Post-Consume Error Semantics

**Files:**

- Modify: `tests/test_publish_attempt_contracts.py`
- Modify: `tests/test_publish_attempt_repository.py`
- Modify: `tests/test_publish_attempt_pg18.py`
- Modify: `tests/test_publish_attempt_service.py`
- Modify: `src/models/publish_attempt.py`
- Modify: `src/storage/publish_attempt_repository.py`
- Modify: `src/services/publish_attempt.py`
- Generate: `web/src/types/api.generated.ts`
- Regression: `tests/test_openapi_types_drift_guard.py`

**Interfaces:**

- Adds only `publish_connector_not_ready_after_consume` and `publish_connector_simulated`.
- `simulated` is validated before platform/success. `simulated=True` is deterministic local policy failure; missing/non-bool simulated truth is ambiguous.
- A typed credential race after consume becomes durable `failed`; any outcome ambiguity remains durable `ambiguous`.
- No state/schema/migration/retry/acceptance restoration change.

- [x] **Step 1: Write RED model/repository vocabulary tests**

Update `test_publish_attempt_aliases_are_exact()` in `tests/test_publish_attempt_contracts.py` so `PublishAttemptErrorCode` is exactly:

~~~python
    assert get_args(PublishAttemptErrorCode) == (
        "publish_connector_not_ready",
        "publish_connector_not_ready_after_consume",
        "publish_connector_simulated",
        "publish_attempt_store_unavailable",
        "acceptance_not_found",
        "acceptance_expired",
        "acceptance_not_available",
        "acceptance_artifact_integrity_mismatch",
        "acceptance_store_unavailable",
        "publish_artifact_unavailable_after_consume",
        "publish_attempt_state_unknown",
        "publish_connector_failed",
        "publish_outcome_ambiguous",
    )
~~~

Add both codes to valid `failed` projections in `tests/test_publish_attempt_repository.py`, and add these wrong-state cases to `test_error_codes_are_bound_to_exact_terminal_state`:

~~~python
        (
            "authorization_failed",
            "prepared",
            "publish_connector_not_ready_after_consume",
        ),
        ("ambiguous", "acceptance_consumed", "publish_connector_simulated"),
~~~

Extend the PG18 branch loop in `tests/test_publish_attempt_pg18.py` to include:

~~~python
        ("failed", "publish_connector_not_ready_after_consume"),
        ("failed", "publish_connector_simulated"),
~~~

- [x] **Step 2: Write the complete service outcome-matrix RED**

First add `"simulated": False` to `FakePublisher`'s default success mapping and all existing intentionally real success/failure fixture mappings in `tests/test_publish_attempt_service.py`.

Append:

~~~python
@pytest.mark.asyncio
@pytest.mark.parametrize("success", [True, False])
async def test_simulated_connector_result_is_durable_failed_after_consume(
    success: bool,
    tmp_path: Path,
) -> None:
    _, PublishAttemptError = _service_symbols()
    harness = _build_harness(
        tmp_path,
        publisher_result={
            "simulated": True,
            "success": success,
            "platform": "shopify",
            "post_id": "must-not-be-trusted",
        },
    )

    with pytest.raises(PublishAttemptError) as error:
        await harness.service.execute(
            auth=_auth(),
            request=_request(),
            route_kind="canonical",
        )

    assert error.value.status_code == 502
    assert error.value.code == "publish_connector_simulated"
    assert error.value.detail.acceptance_consumed is True
    assert error.value.detail.retry_allowed is False
    assert harness.publisher.call_count == 1
    row = _only_record(harness.repository)
    assert row["status"] == "failed"
    assert row["error"] == "publish_connector_simulated"
    assert row["post_id"] is None


@pytest.mark.asyncio
async def test_known_simulated_dependency_is_blocked_before_attempt_or_consume(
    tmp_path: Path,
) -> None:
    _, PublishAttemptError = _service_symbols()
    harness = _build_harness(
        tmp_path,
        readiness_ready=False,
        publisher_result={"simulated": True, "success": True},
    )

    with pytest.raises(PublishAttemptError) as error:
        await harness.service.execute(
            auth=_auth(),
            request=_request(),
            route_kind="canonical",
        )

    assert error.value.status_code == 503
    assert error.value.code == "publish_connector_not_ready"
    assert error.value.detail.acceptance_consumed is False
    assert error.value.detail.retry_allowed is True
    assert harness.repository.records == {}
    assert harness.acceptance.consume_calls == 0
    assert harness.publisher.call_count == 0


@pytest.mark.asyncio
async def test_post_consume_credential_race_is_failed_without_retry_or_restore(
    tmp_path: Path,
) -> None:
    from src.connectors.base import ConnectorCredentialNotReady

    _, PublishAttemptError = _service_symbols()
    harness = _build_harness(
        tmp_path,
        publisher_error=ConnectorCredentialNotReady("missing_credentials"),
    )

    with pytest.raises(PublishAttemptError) as error:
        await harness.service.execute(
            auth=_auth(),
            request=_request(),
            route_kind="canonical",
        )

    assert error.value.status_code == 502
    assert error.value.code == "publish_connector_not_ready_after_consume"
    assert error.value.detail.acceptance_consumed is True
    assert error.value.detail.retry_allowed is False
    assert harness.publisher.call_count == 1
    assert harness.acceptance.consume_calls == 1
    row = _only_record(harness.repository)
    assert row["status"] == "failed"
    assert row["error"] == "publish_connector_not_ready_after_consume"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "connector_result",
    [
        {},
        {"simulated": None, "success": True},
        {"simulated": 0, "success": True},
        {"simulated": "false", "success": True},
        {"simulated": False},
        {"simulated": False, "success": 1},
        {"simulated": False, "success": True, "platform": "shopify"},
        {"simulated": False, "success": True, "post_id": "unsafe\npost"},
        {"simulated": False, "success": True, "url": "file:///private/final.mp4"},
    ],
)
async def test_missing_or_malformed_truth_is_durable_ambiguous(
    connector_result: dict[str, Any],
    tmp_path: Path,
) -> None:
    _, PublishAttemptError = _service_symbols()
    harness = _build_harness(tmp_path, publisher_result=connector_result)

    with pytest.raises(PublishAttemptError) as error:
        await harness.service.execute(
            auth=_auth(),
            request=_request(),
            route_kind="canonical",
        )

    assert error.value.code == "publish_outcome_ambiguous"
    assert error.value.detail.acceptance_consumed is True
    assert error.value.detail.retry_allowed is False
    row = _only_record(harness.repository)
    assert row["status"] == "ambiguous"
    assert row["error"] == "publish_outcome_ambiguous"
    assert harness.publisher.call_count == 1


@pytest.mark.asyncio
async def test_typed_connector_ambiguity_remains_durable_ambiguous(
    tmp_path: Path,
) -> None:
    from src.connectors.base import ConnectorOutcomeAmbiguous

    _, PublishAttemptError = _service_symbols()
    harness = _build_harness(
        tmp_path,
        publisher_error=ConnectorOutcomeAmbiguous(),
    )

    with pytest.raises(PublishAttemptError) as error:
        await harness.service.execute(
            auth=_auth(),
            request=_request(),
            route_kind="canonical",
        )

    assert error.value.code == "publish_outcome_ambiguous"
    assert _only_record(harness.repository)["status"] == "ambiguous"
    assert harness.publisher.call_count == 1
~~~

Update the existing deterministic-false fixture to include `"simulated": False`. In `test_malformed_or_contradictory_connector_result_is_ambiguous`, retain one mapping with missing `simulated`, but add `simulated=False` to cases intended to test success/platform/URL rather than simulation truth. Apply the same fixture migration in `test_terminal_persistence_failure_is_nonretryable_state_unknown`.

- [x] **Step 3: Run Task 4 RED gates**

Run:

~~~bash
.venv/bin/python -m pytest tests/test_publish_attempt_contracts.py tests/test_publish_attempt_repository.py -k 'error or terminal or aliases' tests/test_publish_attempt_service.py -k 'simulated or credential_race or malformed_truth or connector_false or connector_ambiguity' -q
~~~

Expected: the two codes are rejected, `simulated=True` can still reach published/other legacy validation, and typed credential loss is still collapsed into ambiguous.

- [x] **Step 4: Add exactly the two approved error codes**

In `src/models/publish_attempt.py`, insert after `publish_connector_not_ready`:

~~~python
    "publish_connector_not_ready_after_consume",
    "publish_connector_simulated",
~~~

In `src/storage/publish_attempt_repository.py`, add both to `ALLOWED_ERROR_CODES`, and add both only to `ERROR_CODES_BY_STATUS["failed"]`. Do not add them to `authorization_failed` or `ambiguous`; do not change `ALLOWED_STATUSES`, `LEGAL_TRANSITIONS`, SQL, or migration files.

- [x] **Step 5: Add one stable post-consume failed helper**

Import `ConnectorCredentialNotReady` and `ConnectorOutcomeAmbiguous` in `src/services/publish_attempt.py`, then add immediately before `_persist_ambiguous_or_unknown()`:

~~~python
    async def _fail_connector_after_consume(
        self,
        *,
        tenant_id: str,
        attempt_id: str,
        platform: str,
        trace_id: str,
        code: Literal[
            "publish_connector_not_ready_after_consume",
            "publish_connector_simulated",
        ],
        cause: Exception | None = None,
    ) -> NoReturn:
        await self._persist_terminal_or_unknown(
            tenant_id=tenant_id,
            attempt_id=attempt_id,
            platform=platform,
            new_status="failed",
            error_code=code,
            trace_id=trace_id,
        )
        self._raise_error(
            status_code=502,
            code=code,
            attempt_id=attempt_id,
            acceptance_consumed=True,
            retry_allowed=False,
            platform=platform,
            trace_id=trace_id,
            cause=cause,
        )
~~~

- [x] **Step 6: Replace service connector-result projection in fixed order**

Replace `_publish_once_and_persist()` with:

~~~python
    async def _publish_once_and_persist(
        self,
        *,
        tenant_id: str,
        attempt_id: str,
        request: PublishAttemptRequest,
        connector_content: dict[str, Any],
        trace_id: str,
    ) -> PublishAttemptResponse:
        try:
            connector_result = await self.publisher(
                request.platform,
                connector_content,
            )
        except ConnectorCredentialNotReady as exc:
            await self._fail_connector_after_consume(
                tenant_id=tenant_id,
                attempt_id=attempt_id,
                platform=request.platform,
                trace_id=trace_id,
                code="publish_connector_not_ready_after_consume",
                cause=exc,
            )
        except ConnectorOutcomeAmbiguous as exc:
            await self._persist_ambiguous_or_unknown(
                tenant_id=tenant_id,
                attempt_id=attempt_id,
                platform=request.platform,
                trace_id=trace_id,
                cause=exc,
            )
        except Exception as exc:
            await self._persist_ambiguous_or_unknown(
                tenant_id=tenant_id,
                attempt_id=attempt_id,
                platform=request.platform,
                trace_id=trace_id,
                cause=exc,
            )

        try:
            if not isinstance(connector_result, Mapping):
                raise ValueError("connector result is not a mapping")
            simulated = connector_result.get("simulated", _MISSING)
            if type(simulated) is not bool:
                raise ValueError("connector simulated truth is invalid")
            if simulated is True:
                await self._fail_connector_after_consume(
                    tenant_id=tenant_id,
                    attempt_id=attempt_id,
                    platform=request.platform,
                    trace_id=trace_id,
                    code="publish_connector_simulated",
                )

            reported_platform = connector_result.get("platform", _MISSING)
            if reported_platform is not _MISSING and (
                not isinstance(reported_platform, str)
                or reported_platform != request.platform
            ):
                raise ValueError("connector platform is contradictory")
            success = connector_result.get("success", _MISSING)
            if type(success) is not bool:
                raise ValueError("connector success truth is invalid")
            if success is False:
                await self._persist_terminal_or_unknown(
                    tenant_id=tenant_id,
                    attempt_id=attempt_id,
                    platform=request.platform,
                    new_status="failed",
                    error_code="publish_connector_failed",
                    trace_id=trace_id,
                )
                self._raise_error(
                    status_code=502,
                    code="publish_connector_failed",
                    attempt_id=attempt_id,
                    acceptance_consumed=True,
                    retry_allowed=False,
                    platform=request.platform,
                    trace_id=trace_id,
                )

            response = PublishAttemptResponse(
                publish_attempt_id=attempt_id,
                acceptance_id=request.acceptance_id,
                platform=request.platform,
                status="published",
                success=True,
                post_id=connector_result.get("post_id"),
                post_url=connector_result.get("url"),
                acceptance_consumed=True,
                retry_allowed=False,
            )
        except PublishAttemptError:
            raise
        except (AttributeError, TypeError, ValueError, ValidationError) as exc:
            await self._persist_ambiguous_or_unknown(
                tenant_id=tenant_id,
                attempt_id=attempt_id,
                platform=request.platform,
                trace_id=trace_id,
                cause=exc,
            )

        await self._persist_terminal_or_unknown(
            tenant_id=tenant_id,
            attempt_id=attempt_id,
            platform=request.platform,
            new_status="published",
            post_id=response.post_id,
            url=response.post_url,
            trace_id=trace_id,
        )
        return response
~~~

- [x] **Step 7: Regenerate the exact OpenAPI TypeScript enum**

Run only the existing generator after the backend model tests are green:

~~~bash
cd web && npm run typegen:api
cd web && npm run check:api-types
~~~

Inspect the generated diff. The only W1-24 semantic change must be the addition of `publish_connector_not_ready_after_consume` and `publish_connector_simulated` to `PublishAttemptErrorDetail.code`; do not hand-edit the generated file.

- [x] **Step 8: Run Task 4 GREEN, SQLite, OpenAPI, and PG18 collection gates**

Run:

~~~bash
.venv/bin/python -m pytest tests/test_publish_attempt_contracts.py tests/test_publish_attempt_repository.py tests/test_publish_attempt_service.py tests/test_openapi_types_drift_guard.py -q
.venv/bin/python -m pytest tests/test_publish_attempt_pg18.py --collect-only -q
.venv/bin/python -m ruff check src/models/publish_attempt.py src/storage/publish_attempt_repository.py src/services/publish_attempt.py tests/test_publish_attempt_contracts.py tests/test_publish_attempt_repository.py tests/test_publish_attempt_pg18.py tests/test_publish_attempt_service.py tests/test_openapi_types_drift_guard.py
git diff --check -- src/models/publish_attempt.py src/storage/publish_attempt_repository.py src/services/publish_attempt.py tests/test_publish_attempt_contracts.py tests/test_publish_attempt_repository.py tests/test_publish_attempt_pg18.py tests/test_publish_attempt_service.py web/src/types/api.generated.ts
git diff --name-only -- migrations src/storage/migrations
~~~

Expected: focused model/repository/service/OpenAPI tests pass; PG18 test collects without running; generated drift is clean; the final command shows no W1-24 migration/init-SQL changes beyond pre-existing dirty files, which must be distinguished with `git diff` against the pre-task manifest rather than assumed clean.

---

### Task 5: Distribution Status 503/502/200 Truth Projection

**Files:**

- Create: `tests/test_distribution_status_truth.py`
- Modify: `src/routers/distribution.py`
- Regression: `tests/test_publish_acceptance_routes.py`

**Interfaces:**

- Missing/invalid connector credential → HTTP 503 with only `distribution_status_connector_not_ready`.
- Upstream, parsing, injected simulation, or malformed status → HTTP 502 with only `distribution_status_unavailable`.
- Trusted real `unknown`/processing/published → HTTP 200 and exact `simulated=False`.
- `/distribution/platforms` retains shape and derives `connected` from strict shared readiness.

- [x] **Step 1: Write authenticated zero-network status RED tests**

Create `tests/test_distribution_status_truth.py`:

~~~python
from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient, Response

from src.connectors.base import (
    ConnectorCredentialNotReady,
    ConnectorStatusUnavailable,
)
from src.routers._deps import verify_api_key


class FakeStatusConnector:
    def __init__(
        self,
        *,
        result: Any = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.calls: list[str] = []

    async def get_status(self, post_id: str) -> Any:
        self.calls.append(post_id)
        if self.error is not None:
            raise self.error
        return self.result


@pytest.fixture(autouse=True)
def bypass_status_auth() -> Iterator[None]:
    from src.api import app

    app.dependency_overrides[verify_api_key] = lambda: True
    try:
        yield
    finally:
        app.dependency_overrides.pop(verify_api_key, None)


async def _get(path: str) -> Response:
    from src.api import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        return await client.get(path)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "extra"),
    [
        ("unknown", {"views": 0}),
        ("PROCESSING", {"preview_url": ""}),
        ("published", {}),
    ],
)
async def test_status_returns_only_trusted_real_state(
    status: str,
    extra: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.connectors import registry

    connector = FakeStatusConnector(
        result={
            "post_id": "post-fixture",
            "status": status,
            "simulated": False,
            **extra,
        }
    )
    monkeypatch.setattr(registry, "get_connector", lambda _: connector)

    response = await _get("/distribution/status/tiktok/post-fixture")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["post_id"] == "post-fixture"
    assert payload["status"] == status
    assert payload["simulated"] is False
    assert connector.calls == ["post-fixture"]


@pytest.mark.asyncio
async def test_status_success_drops_unknown_provider_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.connectors import registry

    connector = FakeStatusConnector(
        result={
            "post_id": "post-fixture",
            "status": "published",
            "simulated": False,
            "views": 3,
            "raw_body": "must-not-leave-connector-boundary",
            "credential": "must-not-leave-connector-boundary",
        }
    )
    monkeypatch.setattr(registry, "get_connector", lambda _: connector)

    response = await _get("/distribution/status/tiktok/post-fixture")

    assert response.status_code == 200
    payload = response.json()
    assert payload["views"] == 3
    assert "raw_body" not in payload
    assert "credential" not in payload


@pytest.mark.asyncio
async def test_status_missing_credentials_is_stable_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.connectors import registry

    connector = FakeStatusConnector(
        error=ConnectorCredentialNotReady("missing_credentials")
    )
    monkeypatch.setattr(registry, "get_connector", lambda _: connector)

    response = await _get("/distribution/status/tiktok/post-fixture")

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "distribution_status_connector_not_ready"
    }
    assert connector.calls == ["post-fixture"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        ConnectorStatusUnavailable(),
        TimeoutError("raw-timeout-secret"),
        RuntimeError("raw-provider-body-secret"),
    ],
)
async def test_status_unavailable_is_stable_502_without_raw_text(
    error: Exception,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.connectors import registry

    connector = FakeStatusConnector(error=error)
    monkeypatch.setattr(registry, "get_connector", lambda _: connector)

    response = await _get("/distribution/status/tiktok/post-fixture")

    assert response.status_code == 502
    assert response.json()["detail"] == {
        "code": "distribution_status_unavailable"
    }
    evidence = response.text + caplog.text
    assert "raw-timeout-secret" not in evidence
    assert "raw-provider-body-secret" not in evidence


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result",
    [
        None,
        [],
        {},
        {"post_id": "post-fixture", "status": "published"},
        {"post_id": "post-fixture", "status": "published", "simulated": True},
        {"post_id": "post-fixture", "status": "published", "simulated": 0},
        {"post_id": "other", "status": "published", "simulated": False},
        {"post_id": "post-fixture", "status": "", "simulated": False},
        {"post_id": "post-fixture", "status": 1, "simulated": False},
    ],
)
async def test_status_rejects_malformed_or_simulated_injected_results(
    result: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.connectors import registry

    connector = FakeStatusConnector(result=result)
    monkeypatch.setattr(registry, "get_connector", lambda _: connector)

    response = await _get("/distribution/status/tiktok/post-fixture")

    assert response.status_code == 502
    assert response.json()["detail"] == {
        "code": "distribution_status_unavailable"
    }


@pytest.mark.asyncio
async def test_status_preserves_unsupported_platform_client_error() -> None:
    response = await _get("/distribution/status/instagram/post-fixture")
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_status_never_calls_publish_attempt_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.connectors import registry
    from src.routers import distribution

    connector = FakeStatusConnector(
        result={
            "post_id": "post-fixture",
            "status": "unknown",
            "simulated": False,
        }
    )
    monkeypatch.setattr(registry, "get_connector", lambda _: connector)
    monkeypatch.setattr(
        distribution,
        "get_publish_attempt_service",
        lambda: pytest.fail("status must not access the publish ledger"),
    )

    response = await _get("/distribution/status/tiktok/post-fixture")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_platform_listing_uses_strict_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.connectors import registry
    from src.connectors.registry import PublishConnectorReadiness

    def readiness(platform: str) -> PublishConnectorReadiness:
        return PublishConnectorReadiness(
            platform=platform,  # type: ignore[arg-type]
            ready=platform == "tiktok",
            reason=None if platform == "tiktok" else "missing_credentials",
        )

    monkeypatch.setattr(registry, "inspect_publish_readiness", readiness)
    response = await _get("/distribution/platforms")

    assert response.status_code == 200
    assert response.json()[:2] == [
        {"id": "tiktok", "name": "TikTok", "connected": True},
        {"id": "shopify", "name": "Shopify", "connected": False},
    ]
~~~

- [x] **Step 2: Run the status-route RED gate**

Run:

~~~bash
.venv/bin/python -m pytest tests/test_distribution_status_truth.py -q
~~~

Expected: missing credentials/generic failures still project 500 or mock 200, injected simulated/malformed mappings pass through, and platform listing imports `_is_mock_mode`.

- [x] **Step 3: Add a strict status-result projection helper**

In `src/routers/distribution.py`, add top-level `logging`, `Mapping`, `Any`, and typed connector-error imports. Add:

~~~python
logger = logging.getLogger(__name__)
_STATUS_MISSING = object()
_STATUS_FIELDS = {
    "tiktok": frozenset(
        {"post_id", "status", "views", "likes", "comments", "shares", "simulated"}
    ),
    "shopify": frozenset({"post_id", "status", "preview_url", "simulated"}),
}


def _validate_status_result(
    *,
    platform: str,
    post_id: str,
    result: object,
) -> dict[str, Any]:
    if not isinstance(result, Mapping):
        raise ConnectorStatusUnavailable
    simulated = result.get("simulated", _STATUS_MISSING)
    if type(simulated) is not bool or simulated is not False:
        raise ConnectorStatusUnavailable
    if result.get("post_id") != post_id:
        raise ConnectorStatusUnavailable
    status = result.get("status")
    if not isinstance(status, str) or not status.strip():
        raise ConnectorStatusUnavailable
    allowed = _STATUS_FIELDS.get(platform)
    if allowed is None:
        raise ConnectorStatusUnavailable
    return {key: value for key, value in result.items() if key in allowed}
~~~

- [x] **Step 4: Replace the route's broad 500 projection**

Replace `distribution_status()` with:

~~~python
@router.get(
    "/distribution/status/{platform}/{post_id}",
    dependencies=[Depends(verify_api_key)],
)
async def distribution_status(platform: str, post_id: str) -> dict[str, Any]:
    from src.connectors.registry import get_connector

    try:
        connector = get_connector(platform)
        result = await connector.get_status(post_id)
        return _validate_status_result(
            platform=platform,
            post_id=post_id,
            result=result,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=_safe_error(exc)) from None
    except ConnectorCredentialNotReady:
        raise HTTPException(
            status_code=503,
            detail={"code": "distribution_status_connector_not_ready"},
        ) from None
    except ConnectorStatusUnavailable as exc:
        logger.warning(
            "distribution_status_unavailable platform=%s error_class=%s",
            platform,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=502,
            detail={"code": "distribution_status_unavailable"},
        ) from None
    except Exception as exc:
        logger.warning(
            "distribution_status_unavailable platform=%s error_class=%s",
            platform,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=502,
            detail={"code": "distribution_status_unavailable"},
        ) from None
~~~

- [x] **Step 5: Make platform listing reuse readiness**

Replace `distribution_platforms()` body with:

~~~python
    from src.connectors.registry import inspect_publish_readiness

    return [
        {
            "id": "tiktok",
            "name": "TikTok",
            "connected": inspect_publish_readiness("tiktok").ready,
        },
        {
            "id": "shopify",
            "name": "Shopify",
            "connected": inspect_publish_readiness("shopify").ready,
        },
    ]
~~~

- [x] **Step 6: Run Task 5 GREEN and route-auth regression**

Run:

~~~bash
.venv/bin/python -m pytest tests/test_distribution_status_truth.py tests/test_publish_acceptance_routes.py -q
.venv/bin/python -m ruff check src/routers/distribution.py tests/test_distribution_status_truth.py tests/test_publish_acceptance_routes.py
git diff --check -- src/routers/distribution.py tests/test_distribution_status_truth.py tests/test_publish_acceptance_routes.py
~~~

Expected: all status and existing publish-route auth/OpenAPI tests pass; status success contains `simulated=false`; errors contain stable code only.

---

### Task 6: Retained PublishEngine Truth and Compatibility Regression

**Files:**

- Create: `tests/test_publish_engine_truth.py`
- Modify: `src/connectors/publish_engine.py`
- Verify only: `web/src/components/api.ts`
- Verify only: `web/src/components/DistributionView.tsx`
- Verify only: `web/src/components/CriticalViews.i18n.test.tsx`
- Verify only: `tests/test_metrics_poller.py`

**Interfaces:**

- `PublishResult` gains exact `simulated: bool`.
- Typed connector credential/outcome exceptions propagate; raw exception strings never become results or logs.
- Injected `simulated=True` becomes a stable local engine failure, never success.
- Missing/non-bool truth is ambiguous; unsupported platforms remain ordered local failures with `simulated=False`.
- The W1-23 service remains registry-backed and is not rewired through `PublishEngine`.

- [x] **Step 1: Write PublishEngine RED tests**

Create `tests/test_publish_engine_truth.py`:

~~~python
from __future__ import annotations

from typing import Any

import pytest

from src.connectors.base import (
    ConnectorCredentialNotReady,
    ConnectorOutcomeAmbiguous,
)
from src.connectors.publish_engine import PublishEngine


class FakeConnector:
    def __init__(
        self,
        *,
        result: Any = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.calls: list[dict[str, Any]] = []

    async def publish(self, content: dict[str, Any]) -> Any:
        self.calls.append(content)
        if self.error is not None:
            raise self.error
        return self.result


@pytest.mark.asyncio
@pytest.mark.parametrize("platform", ["tiktok", "shopify"])
async def test_engine_projects_trusted_real_success_once(platform: str) -> None:
    connector = FakeConnector(
        result={
            "success": True,
            "simulated": False,
            "platform": platform,
            "post_id": "post-fixture",
            "url": "https://example.invalid/post-fixture",
        }
    )
    engine = PublishEngine()
    setattr(engine, f"_{platform}", connector)

    method = getattr(engine, f"publish_to_{platform}")
    result = await method("/fixture/video.mp4", {"hook": "Reviewed"})

    assert result.platform == platform
    assert result.success is True
    assert result.simulated is False
    assert result.post_id == "post-fixture"
    assert result.post_url == "https://example.invalid/post-fixture"
    assert len(connector.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("success", [True, False])
async def test_engine_never_converts_simulated_result_to_success(success: bool) -> None:
    connector = FakeConnector(
        result={"success": success, "simulated": True, "post_id": "fake"}
    )
    engine = PublishEngine()
    engine._tiktok = connector  # type: ignore[assignment]

    result = await engine.publish_to_tiktok("/fixture/video.mp4", {})

    assert result.success is False
    assert result.simulated is True
    assert result.error == "publish_connector_simulated"
    assert result.post_id == ""
    assert len(connector.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result",
    [
        None,
        {},
        {"simulated": 0, "success": True},
        {"simulated": False},
        {"simulated": False, "success": 1},
    ],
)
async def test_engine_rejects_missing_or_nonbool_truth_as_ambiguous(
    result: Any,
) -> None:
    connector = FakeConnector(result=result)
    engine = PublishEngine()
    engine._tiktok = connector  # type: ignore[assignment]

    with pytest.raises(ConnectorOutcomeAmbiguous):
        await engine.publish_to_tiktok("/fixture/video.mp4", {})
    assert len(connector.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        ConnectorCredentialNotReady("missing_credentials"),
        ConnectorOutcomeAmbiguous(),
    ],
)
async def test_engine_propagates_typed_connector_errors_without_retry(
    error: Exception,
) -> None:
    connector = FakeConnector(error=error)
    engine = PublishEngine()
    engine._shopify = connector  # type: ignore[assignment]

    with pytest.raises(type(error)):
        await engine.publish_to_shopify("/fixture/video.mp4", {})
    assert len(connector.calls) == 1


@pytest.mark.asyncio
async def test_engine_unsupported_platform_keeps_order_and_real_local_truth() -> None:
    tiktok = FakeConnector(
        result={"success": False, "simulated": False, "platform": "tiktok"}
    )
    engine = PublishEngine()
    engine._tiktok = tiktok  # type: ignore[assignment]

    results = await engine.publish(
        "/fixture/video.mp4",
        {},
        ["instagram", "tiktok"],
    )

    assert [result.platform for result in results] == ["instagram", "tiktok"]
    assert results[0].success is False
    assert results[0].simulated is False
    assert results[0].error == "unsupported_platform"
    assert results[1].error == "publish_connector_failed"
    assert len(tiktok.calls) == 1


@pytest.mark.asyncio
async def test_engine_does_not_capture_raw_unknown_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sentinel = "raw-provider-secret-shaped-exception"
    connector = FakeConnector(error=RuntimeError(sentinel))
    engine = PublishEngine()
    engine._tiktok = connector  # type: ignore[assignment]

    with pytest.raises(RuntimeError, match=sentinel):
        await engine.publish_to_tiktok("/fixture/video.mp4", {})
    assert sentinel not in caplog.text
    assert len(connector.calls) == 1
~~~

- [x] **Step 2: Run the engine RED gate**

Run:

~~~bash
.venv/bin/python -m pytest tests/test_publish_engine_truth.py -q
~~~

Expected: `PublishResult` lacks simulated truth, broad catches turn typed/unknown exceptions into ordinary results, simulated mappings can become success, and unsupported errors are not stable.

- [x] **Step 3: Add one exact engine result projector**

In `src/connectors/publish_engine.py`, remove `logging`, import `Mapping`, import `ConnectorOutcomeAmbiguous`, and add:

~~~python
_MISSING = object()


def _project_connector_result(
    *,
    platform: str,
    connector_result: object,
) -> PublishResult:
    if not isinstance(connector_result, Mapping):
        raise ConnectorOutcomeAmbiguous
    simulated = connector_result.get("simulated", _MISSING)
    if type(simulated) is not bool:
        raise ConnectorOutcomeAmbiguous
    if simulated is True:
        return PublishResult(
            platform=platform,
            success=False,
            simulated=True,
            error="publish_connector_simulated",
        )
    success = connector_result.get("success", _MISSING)
    if type(success) is not bool:
        raise ConnectorOutcomeAmbiguous
    if success is False:
        return PublishResult(
            platform=platform,
            success=False,
            simulated=False,
            error="publish_connector_failed",
        )
    post_id = connector_result.get("post_id", "")
    post_url = connector_result.get("url", "")
    if not isinstance(post_id, str) or not isinstance(post_url, str):
        raise ConnectorOutcomeAmbiguous
    return PublishResult(
        platform=platform,
        success=True,
        simulated=False,
        post_id=post_id,
        post_url=post_url,
    )
~~~

Because this function references `PublishResult`, place it immediately after the dataclass rather than before it.

- [x] **Step 4: Add simulated truth and remove broad catches**

Make `PublishResult` exactly:

~~~python
@dataclass
class PublishResult:
    platform: str = ""
    success: bool = False
    simulated: bool = False
    post_id: str = ""
    post_url: str = ""
    error: str = ""
~~~

For unsupported platforms, return:

~~~python
                result = PublishResult(
                    platform=platform,
                    success=False,
                    simulated=False,
                    error="unsupported_platform",
                )
~~~

Replace the complete try/except projection in `publish_to_tiktok()` with:

~~~python
        connector_result = await self._tiktok.publish(content)
        return _project_connector_result(
            platform="tiktok",
            connector_result=connector_result,
        )
~~~

Replace the Shopify projection identically with platform `shopify`. Update module/method docstrings to remove all mock-fallback claims. Do not catch typed or unknown exceptions and do not add retries.

- [x] **Step 5: Run engine GREEN and prove service wiring remains unchanged**

Run:

~~~bash
.venv/bin/python -m pytest tests/test_publish_engine_truth.py tests/test_publish_attempt_service.py -q
rg -n 'publisher: Publisher = publish_to_platform|PublishEngine' src/services/publish_attempt.py
.venv/bin/python -m ruff check src/connectors/publish_engine.py tests/test_publish_engine_truth.py
git diff --check -- src/connectors/publish_engine.py tests/test_publish_engine_truth.py
~~~

Expected: engine and service tests pass; grep shows `PublishAttemptService` still defaults directly to `publish_to_platform` and contains no `PublishEngine` dependency.

- [x] **Step 6: Run frontend status-caller and metrics compatibility regression without edits**

Run:

~~~bash
cd web && npm test -- --run src/components/CriticalViews.i18n.test.tsx
cd web && npx tsc --noEmit
.venv/bin/python -m pytest tests/test_metrics_poller.py -q
git diff --name-only -- web/src/components/api.ts web/src/components/DistributionView.tsx web/src/components/CriticalViews.i18n.test.tsx src/tasks/metrics_poller.py
~~~

Expected: tests/typecheck pass. The final command must show no W1-24 edits to these files; if it shows pre-existing dirty changes, compare against the recorded pre-task manifest and do not overwrite them.

---

### Task 7: Governance, Full Local Acceptance, and Evidence Ceiling

**Files:**

- Create: `docs/runbooks/publish-connector-truth.md`
- Modify after all gates pass: `docs/runbooks/publish-connector-truth.md`
- Modify: `docs/runbooks/README.md`
- Modify: `docs/reference/api-endpoints.md`
- Modify: `configs/docs-link-check-scope.txt`
- Modify after all gates pass: `docs/workflows/enterprise-ai-content-all-scenarios-roadmap-20260711.md`
- Modify after all gates pass: `AGENTS.md`

**Interfaces:**

- Records stable operator semantics without presenting local/fake evidence as platform or production acceptance.
- Proves no migration, runtime mock, real HTTP, retry, acceptance restore, frontend product change, or metrics activation.
- Final state is `implementation_complete_local / independent_review_pending`, not `completed_local`.

- [x] **Step 1: Add RED source/governance guards before documentation claims**

Append these guards to `tests/test_publish_connector_truth.py`:

~~~python
def test_runtime_publish_and_status_sources_have_no_mock_or_retry_escape_hatch() -> None:
    import src.connectors.registry as registry_module
    import src.connectors.shopify_connector as shopify_module
    import src.connectors.tiktok_connector as tiktok_module

    sources = "\n".join(
        inspect.getsource(module)
        for module in (registry_module, tiktok_module, shopify_module)
    )
    for forbidden in (
        "_mock_publish",
        "_mock_status",
        "tt_mock_",
        "sp_mock_",
        "mock-store.myshopify.com",
        "missing_credentials_or_mock_mode",
    ):
        assert forbidden not in sources
    publish_and_status = "\n".join(
        (
            inspect.getsource(tiktok_module.TikTokConnector.publish),
            inspect.getsource(tiktok_module.TikTokConnector.get_status),
            inspect.getsource(shopify_module.ShopifyConnector.publish),
            inspect.getsource(shopify_module.ShopifyConnector.get_status),
        )
    )
    assert "ALLOW_MOCK_MODE" not in publish_and_status
    assert "retry" not in publish_and_status.lower()


def test_w1_24_does_not_add_schema_or_attempt_status() -> None:
    from typing import get_args

    from src.models.publish_attempt import PublishAttemptStatus

    assert get_args(PublishAttemptStatus) == (
        "prepared",
        "authorization_failed",
        "acceptance_consumed",
        "published",
        "failed",
        "ambiguous",
    )
~~~

Run:

~~~bash
.venv/bin/python -m pytest tests/test_publish_connector_truth.py -k 'escape_hatch or schema_or_attempt_status' -q
~~~

Expected before Tasks 2-3 are complete: the runtime-mock source guard fails. After Tasks 2-4 it must pass without exclusions.

- [x] **Step 2: Write the operator runbook and API truth**

Create `docs/runbooks/publish-connector-truth.md` with this exact frontmatter and section contract:

~~~markdown
---
title: Publish Connector Truth and Fail-Closed Operations
doc_type: runbook
module: backend
topic: publish-connector-truth
status: active
created: 2026-07-14
updated: 2026-07-14
owner: self
source: human+ai
---

# Publish Connector Truth and Fail-Closed Operations

## Scope

This runbook covers W1-24 TikTok/Shopify publish credential truth, connector result truth, and distribution-status failure semantics. It does not authorize a real connector/status call, production deployment, live publish, receipt acceptance, delivery, retry, or reconciliation.

## Publish outcome matrix

| Observation | Attempt state | Stable code | HTTP | Acceptance | Retry |
|---|---|---|---:|---|---|
| Pre-consume readiness false | no attempt | `publish_connector_not_ready` | 503 | unconsumed | allowed after credential repair |
| Credential lost after consume, zero outbound | `failed` | `publish_connector_not_ready_after_consume` | 502 | consumed | forbidden |
| Real explicit rejection | `failed` | `publish_connector_failed` | 502 | consumed | forbidden |
| Injected simulated result | `failed` | `publish_connector_simulated` | 502 | consumed | forbidden |
| Missing/malformed truth or uncertain mutation | `ambiguous` | `publish_outcome_ambiguous` | 502 | consumed | forbidden |
| Trusted `simulated=false`, `success=true` | `published` | none | 200 | consumed | forbidden |

## Distribution status

- Missing or invalid connector configuration returns 503 with `distribution_status_connector_not_ready`.
- Transport, provider, parse, shape, or simulated-result failure returns 502 with `distribution_status_unavailable`.
- A trusted real `unknown` or processing status is a valid 200 and includes `simulated=false`.
- Status does not read or write acceptance or publish-attempt records.

## Incident handling

Never replay a consumed attempt automatically. For `ambiguous`, reconcile manually against the platform before any new human acceptance is created. Never restore a consumed acceptance.

## Safe rollback

Before rolling back an application version, block publish mutations and distribution status at the gateway. Do not roll back to a version that can fabricate mock `published`. Keep routes blocked until a version satisfying this truth contract is deployed.

## Evidence boundary

W1-24 local tests use fixture credentials, injected connectors, fake transports, and an optional disposable PostgreSQL 18 database. They do not prove credential validity, platform scopes, endpoint correctness, real receipt truth, production deployment, or live publish. Those remain W1-25/W1-26.
~~~

Add the runbook to `docs/runbooks/README.md` and `configs/docs-link-check-scope.txt`. Update `docs/reference/api-endpoints.md` with the exact publish error-code additions and status 503/502/200 mapping. Do not document a new request field or frontend control.

- [x] **Step 3: Run the complete focused backend gate**

Run:

~~~bash
.venv/bin/python -m pytest \
  tests/test_publish_connector_truth.py \
  tests/test_connectors_mock.py \
  tests/test_publish_connector_log_safety.py \
  tests/test_publish_engine_truth.py \
  tests/test_distribution_status_truth.py \
  tests/test_publish_attempt_contracts.py \
  tests/test_publish_attempt_repository.py \
  tests/test_publish_attempt_service.py \
  tests/test_publish_acceptance_routes.py \
  tests/test_publish_acceptance_outcome.py \
  tests/test_openapi_types_drift_guard.py \
  tests/test_metrics_poller.py \
  -q
~~~

Expected: all focused tests pass; no real connector/provider/status call occurs. Record exact pass/skip/deselect counts and warnings rather than copying expected historical counts.

- [x] **Step 4: Run optional disposable PostgreSQL 18 allowlist regression**

Only if Docker is available and the prior W1-23 harness can be reused without changing schema, start the exact loopback-only container:

~~~bash
docker run --rm -d --name ai-video-w1-24-pg18 -e POSTGRES_HOST_AUTH_METHOD=trust -p 127.0.0.1:55439:5432 postgres:18
~~~

Poll `docker exec ai-video-w1-24-pg18 pg_isready -U postgres -d postgres` at most 30 one-second attempts, create only `w1_23_migration`, and load the current local fresh-init schema:

~~~bash
docker exec ai-video-w1-24-pg18 createdb -U postgres w1_23_migration
docker exec -i ai-video-w1-24-pg18 psql -v ON_ERROR_STOP=1 -U postgres -d w1_23_migration < src/storage/migrations/001_init.sql
~~~

Run only the guarded fake-connector PG18 module:

~~~bash
W1_23_PG18_DSN=postgresql://postgres@127.0.0.1:55439/w1_23_migration PYTEST_INCLUDE_HERMETIC_SLOW=1 .venv/bin/python -m pytest tests/test_publish_attempt_pg18.py -m hermetic_slow -q
~~~

Then remove and prove absence:

~~~bash
docker rm -f ai-video-w1-24-pg18
docker ps -a --filter name=ai-video-w1-24-pg18 --format '{{.Names}}'
~~~

Expected: PG18 tests pass, including both new failed-state error codes; final output is empty. If Docker is unavailable, record this gate as unverified rather than replacing it with production or remote database access.

- [x] **Step 5: Run full backend CI with external mutation switches forced off**

Run:

~~~bash
RUN_LIVE_PUBLISH=0 RUN_TOKEN_SMOKE=0 PYTEST_INCLUDE_HERMETIC_SLOW=0 make ci
~~~

Expected: Ruff and the full backend suite pass. Credential-gated external mutation tests remain skipped/deselected; record exact counts and any warning.

- [x] **Step 6: Run the full frontend no-change gate**

Run serially from `web/`:

~~~bash
npm test -- --run
npm run lint
npx tsc --noEmit
npm run check:api-types
npm run build
~~~

Expected: every command passes. Do not run Next dev and build concurrently. No W1-24 frontend product file should be edited.

- [x] **Step 7: Run documentation, static, diff, and secret-safe gates**

Run:

~~~bash
.venv/bin/python -m pytest tests/test_markdown_frontmatter_compliance.py tests/test_docs_link_check_scope.py tests/test_archive_draft_link_drift.py -q
~~~

~~~bash
! rg -n '_mock_publish|_mock_status|tt_mock_|sp_mock_|mock-store\.myshopify\.com|missing_credentials_or_mock_mode' src/connectors src/routers/distribution.py src/services/publish_attempt.py
~~~

~~~bash
! rg -n 'ALLOW_MOCK_MODE' src/connectors/registry.py src/connectors/tiktok_connector.py src/connectors/shopify_connector.py src/routers/distribution.py
~~~

~~~bash
git diff --check
~~~

~~~bash
! rg -n 'TODO|FIXME|TBD|placeholder|pass$' src/connectors/base.py src/connectors/registry.py src/connectors/tiktok_connector.py src/connectors/shopify_connector.py src/connectors/publish_engine.py src/services/publish_attempt.py src/routers/distribution.py tests/test_publish_connector_truth.py tests/test_distribution_status_truth.py tests/test_publish_engine_truth.py docs/runbooks/publish-connector-truth.md
~~~

Expected: both negative guards exit successfully, `git diff --check` is clean, and placeholder scan returns no unresolved implementation marker. An abstract-method `pass` is not allowed because Task 1 uses `raise NotImplementedError`.

Run a scoped sensitive-pattern scan without reading any secret file:

~~~bash
! git diff -- src/connectors src/models/publish_attempt.py src/services/publish_attempt.py src/storage/publish_attempt_repository.py src/routers/distribution.py tests docs/runbooks/publish-connector-truth.md | rg -n 'BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY|ghp_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|password[[:space:]]*='
~~~

Expected: no real secret/private-key match. Fixture-token literals are permitted only in tests and must never be logged.

- [x] **Step 8: Perform two main-thread self-reviews**

Review 1 — specification trace:

- Trace every section 5-10 invariant/acceptance criterion in the approved spec to one implementation location and one fresh test.
- Verify `simulated` validation order, pre/post-consume distinction, exact status HTTP projection, one connector call, and no acceptance restore.
- Verify every affected existing fake result now declares `simulated` intentionally.

Review 2 — adversarial safety/compatibility:

- Credential unset/blank/whitespace/partial/invalid host; canonical versus legacy Shopify token.
- Timeout/disconnect/5xx/parse/missing field; 4xx/GraphQL verified rejection; ancillary association failure.
- Raw error/token/path/body/log leakage; malformed injected values including `0`, `1`, strings, lists, and cross-platform results.
- W1-22/W1-23 auth, consume, CAS, concurrency, OpenAPI, frontend build, and metrics regressions.
- No migration/status/frontend product/deploy/provider/real connector expansion.

Fix any finding through a new RED/GREEN cycle, rerun the narrow and affected broad gates, and record it. Because the user prohibited subagents, write `independent_review=false` and do not label this step independent review.

- [x] **Step 9: Write final local evidence and synchronize state only after all mandatory gates pass**

Update the tracked roadmap and connector-truth runbook with:

- approved spec and plan paths;
- scoped file manifest;
- fresh RED failures and subsequent GREEN commands/results;
- focused/full backend, optional PG18, frontend, docs/static/diff/secret scan evidence;
- outcome-matrix trace and explicit connector call-count evidence;
- `independent_review=false`;
- `implementation_complete_local / independent_review_pending`;
- fixed boundaries: `production unchanged`, `provider_call=false`, `real_connector_call=false`, `external_status_call=false`, `live_publish=false`, `database_write=local-test-only`;
- residual W1-25/W1-26 work and every unverified item.

Then synchronize:

- roadmap W1-24 → unchecked `implementation_complete_local / independent_review_pending`, never checked `completed_local`;
- `AGENTS.md` → concise W1-24 local implementation fact plus production/real-call/reviewer ceiling;
- tracked roadmap and connector-truth runbook → exact fresh evidence and next gate;
- keep W1-25 and W1-26 pending and separately authorized.

- [x] **Step 10: Re-run post-synchronization verification and stop**

Run:

~~~bash
.venv/bin/python -m pytest tests/test_markdown_frontmatter_compliance.py tests/test_docs_link_check_scope.py tests/test_archive_draft_link_drift.py -q
git diff --check
git status --short --branch
~~~

Expected: docs governance and diff checks pass; status shows only the preserved pre-existing dirty worktree plus the approved W1-24 manifest. Do not stage, commit, push, open a PR, deploy, call a connector/status endpoint, or mark W1-24 `completed_local`.

---

## Completion Checklist

- [x] Approved W1-24 spec is still the single source of design truth.
- [x] Strict credential validator parity covers TikTok and Shopify unset/blank/partial/invalid cases.
- [x] Runtime publish/status mock helpers and identifiers are absent.
- [x] Every deterministic real connector mapping has exact `simulated=False`.
- [x] Service validates `simulated` before platform/success and persists the approved outcome matrix.
- [x] Post-consume credential race and simulated leak use the two approved stable failed-state codes.
- [x] Status route returns only stable 503/502 or trusted real 200.
- [x] PublishEngine propagates typed exceptions and never returns raw exception text.
- [x] No retry, second connector call, acceptance restore, new state, schema, migration, dependency, or frontend product change.
- [x] Focused backend, full backend, frontend, docs/static/diff/sensitive scans pass with fresh evidence.
- [x] Disposable PG18 regression passes or is explicitly recorded unverified without remote substitution.
- [x] Two main-thread self-reviews are complete; `independent_review=false` remains explicit.
- [x] State documents stop at `implementation_complete_local / independent_review_pending`.
- [x] Boundary audit is explicit: no stage, commit, push, PR, SSH, deploy, production DB, credentialed real provider/connector/status, live publish, delivery, or metrics live pull occurred; the two fixture-only RED network attempts before the construction guard are disclosed in Task 11 evidence.
