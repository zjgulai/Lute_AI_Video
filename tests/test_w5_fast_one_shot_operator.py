from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

import pytest

from src.operations.w5_fast_one_shot import (
    BackendResponse,
    EvidenceStore,
    OperatorBlocked,
    TransportAmbiguous,
    assert_backend_route_contract,
    execute_submit_once,
    poll_status,
    run_with_provider_off_restore,
    safe_ledger_projection,
)


class FakeGateway:
    def __init__(
        self,
        *,
        submit_response: BackendResponse | None = None,
        submit_error: Exception | None = None,
        statuses: list[BackendResponse] | None = None,
    ) -> None:
        self.submit_response = submit_response or BackendResponse(
            status_code=200,
            payload={
                "task_id": "fast_fixture_001",
                "status": "queued",
                "started_at_unix": 1,
                "idempotent_replay": False,
            },
        )
        self.submit_error = submit_error
        self.statuses = list(statuses or [])
        self.submit_calls = 0
        self.status_calls = 0
        self.marker_path: Path | None = None

    def submit(self, *, payload: bytes, raw_key: str, api_key: str) -> BackendResponse:
        assert payload
        assert raw_key == "a" * 64
        assert api_key == "fixture-api-key"
        assert self.marker_path is not None and self.marker_path.exists()
        self.submit_calls += 1
        if self.submit_error is not None:
            raise self.submit_error
        return self.submit_response

    def status(self, *, task_id: str, api_key: str) -> BackendResponse:
        assert task_id == "fast_fixture_001"
        assert api_key == "fixture-api-key"
        self.status_calls += 1
        if not self.statuses:
            raise AssertionError("unexpected extra poll")
        return self.statuses.pop(0)


def _authority() -> dict[str, Any]:
    return {
        "activation_id": "w5fastact:fixture-001",
        "binding_id": "w5fastbind:fixture-001",
        "tenant_id": "tenant-alpha",
        "submission_cap": 1,
        "automatic_retry_cap": 0,
        "provider_max_retries": 0,
        "artifact_disposition": "pending_review",
        "publish_allowed": False,
        "delivery_accepted": False,
    }


def _request() -> dict[str, Any]:
    return {
        "user_prompt": "fixture prompt that must never enter evidence",
        "duration": 15,
        "enable_tts": False,
        "api_keys": {},
        "enable_media_synthesis": True,
        "artifact_disposition": "pending_review",
        "provider_max_retries": 0,
    }


def test_backend_route_contract_accepts_only_canonical_methods() -> None:
    assert_backend_route_contract(
        {
            "/fast/submit": {"post": {}},
            "/fast/status/{task_id}": {"get": {}},
        }
    )


@pytest.mark.parametrize(
    ("paths", "code"),
    [
        ({}, "backend_submit_route_contract_mismatch"),
        ({"/fast/submit": {"post": {}}}, "backend_status_route_contract_mismatch"),
        (
            {
                "/api/fast/submit": {"post": {}},
                "/api/fast/status/{task_id}": {"get": {}},
            },
            "backend_submit_route_contract_mismatch",
        ),
    ],
)
def test_backend_route_contract_rejects_missing_or_proxy_paths(
    paths: dict[str, Any],
    code: str,
) -> None:
    with pytest.raises(OperatorBlocked, match=code):
        assert_backend_route_contract(paths)


def test_submit_creates_marker_before_exactly_one_post(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path)
    gateway = FakeGateway()
    gateway.marker_path = store.path("submit-invoked.json")

    outcome = execute_submit_once(
        store=store,
        gateway=gateway,
        raw_key="a" * 64,
        api_key="fixture-api-key",
        request_payload=_request(),
        authority=_authority(),
        invoked_at_unix=1,
    )

    assert gateway.submit_calls == 1
    assert outcome["submit_state"] == "accepted"
    assert outcome["submit_count"] == 1
    assert outcome["provider_retry_count"] == 0
    assert stat.S_IMODE(store.path("submit-invoked.json").stat().st_mode) == 0o600
    assert stat.S_IMODE(store.path("submit-outcome.json").stat().st_mode) == 0o600
    combined = store.path("submit-invoked.json").read_text() + store.path(
        "submit-outcome.json"
    ).read_text()
    assert "a" * 64 not in combined
    assert "fixture-api-key" not in combined
    assert _request()["user_prompt"] not in combined


def test_existing_marker_blocks_without_post(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path)
    store.create_json("submit-invoked.json", {"status": "already-consumed"})
    gateway = FakeGateway()
    gateway.marker_path = store.path("submit-invoked.json")

    with pytest.raises(OperatorBlocked, match="w5_fast_submit_marker_exists"):
        execute_submit_once(
            store=store,
            gateway=gateway,
            raw_key="a" * 64,
            api_key="fixture-api-key",
            request_payload=_request(),
            authority=_authority(),
            invoked_at_unix=1,
        )

    assert gateway.submit_calls == 0


def test_transport_ambiguity_is_consumed_and_never_retried(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path)
    gateway = FakeGateway(submit_error=TransportAmbiguous("secret upstream text"))
    gateway.marker_path = store.path("submit-invoked.json")

    outcome = execute_submit_once(
        store=store,
        gateway=gateway,
        raw_key="a" * 64,
        api_key="fixture-api-key",
        request_payload=_request(),
        authority=_authority(),
        invoked_at_unix=1,
    )

    assert gateway.submit_calls == 1
    assert outcome == {
        "submit_state": "transport_ambiguous",
        "submit_count": 1,
        "provider_retry_count": 0,
        "safe_error_code": "backend_submit_transport_ambiguous",
    }
    assert "secret upstream text" not in store.path("submit-outcome.json").read_text()


def test_rejected_http_stores_only_allowlisted_safe_fields(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path)
    gateway = FakeGateway(
        submit_response=BackendResponse(
            status_code=409,
            payload={
                "detail": {"code": "w5_fast_binding_mismatch", "secret": "leak"},
                "raw_response": "must-not-survive",
            },
        )
    )
    gateway.marker_path = store.path("submit-invoked.json")

    outcome = execute_submit_once(
        store=store,
        gateway=gateway,
        raw_key="a" * 64,
        api_key="fixture-api-key",
        request_payload=_request(),
        authority=_authority(),
        invoked_at_unix=1,
    )

    assert outcome == {
        "submit_state": "rejected",
        "http_status": 409,
        "submit_count": 1,
        "provider_retry_count": 0,
        "detail_code": "w5_fast_binding_mismatch",
    }
    encoded = store.path("submit-outcome.json").read_text()
    assert "leak" not in encoded
    assert "must-not-survive" not in encoded


def test_poll_is_get_only_finite_and_stores_safe_terminal_projection(
    tmp_path: Path,
) -> None:
    store = EvidenceStore(tmp_path)
    store.create_json(
        "submit-outcome.json",
        {
            "submit_state": "accepted",
            "task_id": "fast_fixture_001",
            "submit_count": 1,
            "provider_retry_count": 0,
        },
    )
    gateway = FakeGateway(
        statuses=[
            BackendResponse(
                200,
                {"task_id": "fast_fixture_001", "status": "running", "stage": "video"},
            ),
            BackendResponse(
                200,
                {
                    "task_id": "fast_fixture_001",
                    "status": "done",
                    "stage": "completed",
                    "lifecycle_status": "completed_bounded",
                    "result": {"prompt": "leak", "video_path": "/private/leak.mp4"},
                },
            ),
        ]
    )

    terminal = poll_status(
        store=store,
        gateway=gateway,
        api_key="fixture-api-key",
        max_polls=2,
        sleep=lambda _seconds: None,
        poll_interval_seconds=0,
    )

    assert gateway.submit_calls == 0
    assert gateway.status_calls == 2
    assert terminal["status"] == "done"
    assert terminal["lifecycle_status"] == "completed_bounded"
    encoded = store.path("terminal-outcome.json").read_text()
    assert "prompt" not in encoded
    assert "/private" not in encoded


def test_poll_rejects_contradictory_task_identity(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path)
    store.create_json(
        "submit-outcome.json",
        {
            "submit_state": "accepted",
            "task_id": "fast_fixture_001",
            "submit_count": 1,
            "provider_retry_count": 0,
        },
    )
    gateway = FakeGateway(
        statuses=[
            BackendResponse(
                200,
                {"task_id": "fast_other_002", "status": "done"},
            )
        ]
    )

    terminal = poll_status(
        store=store,
        gateway=gateway,
        api_key="fixture-api-key",
        max_polls=1,
        sleep=lambda _seconds: None,
        poll_interval_seconds=0,
    )

    assert terminal == {
        "task_id": "fast_fixture_001",
        "status": "poll_invalid",
        "safe_error_code": "backend_status_task_mismatch",
        "poll_count": 1,
    }


@pytest.mark.parametrize("operation_result", [0, 2, 3, 5])
def test_provider_off_restore_runs_for_every_terminal_result(
    operation_result: int,
) -> None:
    events: list[str] = []

    result = run_with_provider_off_restore(
        operation=lambda: events.append("operation") or operation_result,
        restore=lambda: events.append("restore"),
    )

    assert result == operation_result
    assert events == ["operation", "restore"]


def test_provider_off_restore_runs_for_unexpected_failure() -> None:
    events: list[str] = []

    def fail() -> int:
        events.append("operation")
        raise RuntimeError("secret failure")

    with pytest.raises(RuntimeError, match="secret failure"):
        run_with_provider_off_restore(
            operation=fail,
            restore=lambda: events.append("restore"),
        )
    assert events == ["operation", "restore"]


def test_restore_failure_is_not_hidden_by_operation_success() -> None:
    with pytest.raises(OperatorBlocked, match="provider_off_restore_failed"):
        run_with_provider_off_restore(
            operation=lambda: 0,
            restore=lambda: (_ for _ in ()).throw(RuntimeError("restore detail")),
        )


def test_safe_ledger_projection_drops_result_snapshot_and_unknown_fields() -> None:
    projected = safe_ledger_projection(
        {
            "idempotency": {
                "resource_id": "fast_fixture_001",
                "record_status": "completed",
                "stage": "completed",
                "trusted_authorization_ref": "w5fastact:fixture-001",
                "safe_error_code": None,
                "result_snapshot": {"prompt": "leak"},
            },
            "account": {
                "account_id": "acct_fixture",
                "job_id": "fast_fixture_001",
                "cap_usd_nanos": 3_150_000_000,
                "reserved_usd_nanos": 0,
                "settled_usd_nanos": 3_000_000_000,
                "unknown": "leak",
            },
            "attempts": [
                {
                    "logical_operation": "fast.video",
                    "ordinal": 1,
                    "provider": "poyo",
                    "canonical_model": "seedance-2",
                    "state": "settled",
                    "external_task_id": "task_safe_001",
                    "raw_response": "leak",
                }
            ],
        }
    )

    encoded = json.dumps(projected)
    assert "result_snapshot" not in encoded
    assert "unknown" not in encoded
    assert "raw_response" not in encoded
    assert projected["attempts"][0]["state"] == "settled"


def test_evidence_store_is_create_only_regular_and_bounded(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path)
    store.create_json("safe.json", {"status": "ok"})
    with pytest.raises(OperatorBlocked, match="operator_evidence_exists"):
        store.create_json("safe.json", {"status": "overwritten"})
    assert json.loads(store.read_json("safe.json")) == {"status": "ok"}
    assert stat.S_IMODE(store.path("safe.json").stat().st_mode) == 0o600

    link = tmp_path / "linked.json"
    link.symlink_to(store.path("safe.json"))
    with pytest.raises(OperatorBlocked, match="operator_evidence_unavailable"):
        store.read_json("linked.json")

    huge = tmp_path / "huge.json"
    huge.write_bytes(b"{" + b"x" * 70_000 + b"}")
    os.chmod(huge, 0o600)
    with pytest.raises(OperatorBlocked, match="operator_evidence_too_large"):
        store.read_json("huge.json")


def test_evidence_store_rejects_loose_wrong_owner_or_substituted_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loose = tmp_path / "loose"
    loose.mkdir(mode=0o755)
    with pytest.raises(OperatorBlocked, match="operator_evidence_permissions_invalid"):
        EvidenceStore(loose)

    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    actual_uid = os.geteuid()
    monkeypatch.setattr(os, "geteuid", lambda: actual_uid + 1)
    with pytest.raises(OperatorBlocked, match="operator_evidence_permissions_invalid"):
        EvidenceStore(private)
    monkeypatch.setattr(os, "geteuid", lambda: actual_uid)

    store = EvidenceStore(private)
    moved = tmp_path / "moved"
    private.rename(moved)
    private.mkdir(mode=0o700)
    with pytest.raises(OperatorBlocked, match="operator_evidence_permissions_invalid"):
        store.read_json("missing.json")


def test_safe_ledger_projection_omits_corrupt_values_and_rejects_overflow() -> None:
    projected = safe_ledger_projection(
        {
            "idempotency": {
                "resource_id": "/private/leak",
                "record_status": "completed\nsecret",
                "stage": "x" * 300,
                "trusted_authorization_ref": "w5fastact:safe",
                "safe_error_code": "safe_code",
            },
            "account": {
                "account_id": "acct_safe",
                "job_id": "job_safe",
                "cap_usd_nanos": -1,
                "reserved_usd_nanos": 2**63,
                "settled_usd_nanos": 5,
            },
            "attempts": [
                {
                    "logical_operation": "fast.video",
                    "ordinal": 0,
                    "provider": "poyo\nsecret",
                    "canonical_model": "/private/model",
                    "state": "settled",
                    "external_task_id": "/private/task",
                    "reserved_usd_nanos": -1,
                    "settled_usd_nanos": 5,
                    "safe_error_code": "safe_code",
                }
            ],
        }
    )

    encoded = json.dumps(projected)
    assert "/private" not in encoded
    assert "secret" not in encoded
    assert "x" * 300 not in encoded
    assert "cap_usd_nanos" not in projected["account"]
    assert "reserved_usd_nanos" not in projected["account"]
    assert projected["account"]["settled_usd_nanos"] == 5
    assert "ordinal" not in projected["attempts"][0]

    with pytest.raises(OperatorBlocked, match="operator_ledger_projection_invalid"):
        safe_ledger_projection({"attempts": [{} for _ in range(65)]})
