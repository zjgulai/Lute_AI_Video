from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.pipeline.provider_billing_reconciliation import (
    AUTHORIZATION_STATEMENT,
    EXPECTED_PROVIDER_CREDIT_MICRO_UNITS,
    EXPECTED_USD_NANOS,
    W131ExecutionResult,
    build_preflight_report,
    build_private_approval_payload,
    canonical_consumption_marker_path,
    consume_and_execute_once,
    execute_canonical_authorized_live_once,
    execute_canonical_w131_sample,
    parse_private_approval_record,
    reconcile_single_task_charge,
)

NOW = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)


def _approval_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "w1-31-provider-billing-reconciliation.v1",
        "approval_id": "w1_31_calibration_20260718_001",
        "scope": "w1-31-provider-billing-reconciliation",
        "provider": "poyo",
        "model": "gpt-image-2",
        "approved_by": "owner-pray",
        "confirmed_by": "operator-alice",
        "account_readiness_checked_by": "operator-alice",
        "account_readiness_checked_at": "2026-07-18T11:55:00Z",
        "available_credit_micro_units": EXPECTED_PROVIDER_CREDIT_MICRO_UNITS,
        "approved_at": "2026-07-18T11:50:00Z",
        "expires_at": "2026-07-18T12:50:00Z",
        "price_checked_at": "2026-07-18T11:55:00Z",
        "price_evidence_urls": [
            "https://poyo.ai/models/gpt-image-2",
            "https://docs.poyo.ai/api-manual/image-series/gpt-image-2",
            "https://docs.poyo.ai/api-manual/task-management/status",
        ],
        "authorization_statement": AUTHORIZATION_STATEMENT,
        "sample": {
            "workflow": "text-to-image",
            "quality": "low",
            "size": "1:1",
            "effective_resolution": "1K",
            "image_count": 1,
            "prompt_profile_id": "neutral-calibration-cube-v1",
        },
        "budget_limit_usd": "0.01",
        "expected_usd_nanos": EXPECTED_USD_NANOS,
        "expected_provider_credit_micro_units": EXPECTED_PROVIDER_CREDIT_MICRO_UNITS,
        "max_provider_calls": 1,
        "max_retries": 0,
        "production_allowed": False,
        "publish_allowed": False,
        "delivery_allowed": False,
    }
    payload.update(overrides)
    return payload


def _write_record(tmp_path: Path, payload: dict[str, Any] | None = None) -> Path:
    path = tmp_path / "approval.json"
    path.write_text(json.dumps(payload or _approval_payload(), separators=(",", ":")) + "\n")
    return path


def test_exact_private_record_is_accepted(tmp_path: Path) -> None:
    record = parse_private_approval_record(_write_record(tmp_path), now=NOW)

    assert record.approval_id == "w1_31_calibration_20260718_001"
    assert record.approved_by != record.confirmed_by
    assert record.budget_limit_usd == "0.01"
    assert record.max_provider_calls == 1
    assert record.max_retries == 0


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"confirmed_by": "owner-pray"}, "invalid"),
        ({"expires_at": "2026-07-18T11:59:59Z"}, "expired"),
        ({"expires_at": "2026-07-18T14:50:01Z"}, "two-hour"),
        ({"price_checked_at": "2026-07-17T10:00:00Z"}, "price evidence"),
        ({"budget_limit_usd": "0.02"}, "invalid"),
        ({"max_provider_calls": 2}, "invalid"),
        ({"authorization_statement": "同意 W1-31"}, "invalid"),
    ],
)
def test_record_rejects_non_exact_authority(
    tmp_path: Path,
    overrides: dict[str, Any],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        parse_private_approval_record(_write_record(tmp_path, _approval_payload(**overrides)), now=NOW)


def test_record_rejects_unknown_duplicate_and_float_fields(tmp_path: Path) -> None:
    unknown = _approval_payload(extra_authority=True)
    with pytest.raises(ValueError):
        parse_private_approval_record(_write_record(tmp_path, unknown), now=NOW)

    duplicate = _write_record(tmp_path)
    duplicate.write_text(
        json.dumps(_approval_payload(), separators=(",", ":"))[:-1] + ',"max_retries":0}\n'
    )
    with pytest.raises(ValueError, match="duplicate"):
        parse_private_approval_record(duplicate, now=NOW)

    floated = _approval_payload()
    floated["expected_usd_nanos"] = 10_000_000.0
    with pytest.raises(ValueError):
        parse_private_approval_record(_write_record(tmp_path, floated), now=NOW)


def test_preflight_checks_key_presence_without_leaking_value(tmp_path: Path) -> None:
    path = _write_record(tmp_path)
    secret = "fixture-key-must-never-appear"

    blocked = build_preflight_report(
        approval_record_path=path,
        env={},
        now=NOW,
    )
    ready = build_preflight_report(
        approval_record_path=path,
        env={"POYO_API_KEY": secret},
        now=NOW,
    )

    assert blocked.blocked is True
    assert blocked.provider_call_allowed is False
    assert ready.blocked is False
    assert ready.provider_call_allowed is True
    assert secret not in ready.model_dump_json()


def test_invalid_record_never_claims_one_shot_authority_pass(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid-approval.json"
    invalid.write_text("{}\n")

    report = build_preflight_report(
        approval_record_path=invalid,
        env={"POYO_API_KEY": "fixture-key"},
        now=NOW,
    )

    one_shot = next(check for check in report.checks if check.name == "one_shot_authority")
    assert report.blocked is True
    assert report.approval_id is None
    assert one_shot.status == "block"
    assert one_shot.detail == "cannot evaluate one-shot authority without a valid approval record"


def test_consumption_marker_is_stable_for_approval_identity(tmp_path: Path) -> None:
    record = parse_private_approval_record(_write_record(tmp_path), now=NOW)

    marker = canonical_consumption_marker_path(record)

    assert marker.name == "w1_31_calibration_20260718_001.json"
    assert marker.parent.name == "w1-31-authority-consumption"


def test_preflight_blocks_a_consumed_canonical_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.pipeline import provider_billing_reconciliation as reconciliation

    record_path = _write_record(tmp_path)
    record = parse_private_approval_record(record_path, now=NOW)
    monkeypatch.setattr(reconciliation, "PRIVATE_REPO_DIR", tmp_path / "private")
    marker = canonical_consumption_marker_path(record)
    marker.parent.mkdir(parents=True)
    marker.write_text("{}\n")

    report = build_preflight_report(
        approval_record_path=record_path,
        env={"POYO_API_KEY": "fixture-key"},
        now=NOW,
    )

    assert report.blocked is True
    assert report.provider_call_allowed is False
    assert any(check.name == "one_shot_authority" and check.status == "block" for check in report.checks)


@pytest.mark.asyncio
async def test_one_shot_marker_exists_before_callback_and_blocks_replay(tmp_path: Path) -> None:
    record = parse_private_approval_record(_write_record(tmp_path), now=NOW)
    marker = tmp_path / "consumed.json"
    calls = 0

    async def execute() -> W131ExecutionResult:
        nonlocal calls
        calls += 1
        assert marker.exists()
        return W131ExecutionResult(
            external_task_id="task_safe_001",
            attempt_state="settled",
            account_reserved_usd_nanos=0,
            account_settled_usd_nanos=EXPECTED_USD_NANOS,
            attempt_reserved_usd_nanos=EXPECTED_USD_NANOS,
            attempt_settled_usd_nanos=EXPECTED_USD_NANOS,
            provider_reported_credit_micro_units=EXPECTED_PROVIDER_CREDIT_MICRO_UNITS,
            artifact_sha256="a" * 64,
            artifact_size_bytes=123,
        )

    report = await consume_and_execute_once(record=record, marker_path=marker, execute=execute)

    assert calls == 1
    assert report.single_task_charge_reconciled is True
    assert report.invoice_reconciliation is False
    assert report.evidence_level == "L2-fixture-or-dry-run"
    assert report.provider_call_executed is False
    assert stat_mode(marker) == 0o600
    with pytest.raises(FileExistsError):
        await consume_and_execute_once(record=record, marker_path=marker, execute=execute)
    assert calls == 1


def test_three_way_reconciliation_fails_closed_on_any_mismatch() -> None:
    exact = W131ExecutionResult(
        external_task_id="task_safe_001",
        attempt_state="settled",
        account_reserved_usd_nanos=0,
        account_settled_usd_nanos=EXPECTED_USD_NANOS,
        attempt_reserved_usd_nanos=EXPECTED_USD_NANOS,
        attempt_settled_usd_nanos=EXPECTED_USD_NANOS,
        provider_reported_credit_micro_units=EXPECTED_PROVIDER_CREDIT_MICRO_UNITS,
        artifact_sha256="b" * 64,
        artifact_size_bytes=123,
    )

    passed = reconcile_single_task_charge(exact)
    failed = reconcile_single_task_charge(
        exact.model_copy(update={"provider_reported_credit_micro_units": 3_000_000})
    )

    assert passed.single_task_charge_reconciled is True
    assert failed.single_task_charge_reconciled is False
    assert "provider_credit_mismatch" in failed.mismatch_codes
    assert passed.invoice_reconciliation is False
    assert passed.evidence_level == "L2-fixture-or-dry-run"
    assert passed.provider_call_executed is False


@pytest.mark.asyncio
async def test_canonical_authorized_live_wrapper_is_permanently_retired(
    tmp_path: Path,
) -> None:
    record = parse_private_approval_record(_write_record(tmp_path), now=NOW)

    with pytest.raises(RuntimeError, match="w1_31_execution_retired"):
        await execute_canonical_authorized_live_once(
            record=record,
            run_directory=tmp_path / "run",
        )


def test_summary_has_no_prompt_secret_url_or_absolute_path() -> None:
    result = W131ExecutionResult(
        external_task_id="task_safe_001",
        attempt_state="settled",
        account_reserved_usd_nanos=0,
        account_settled_usd_nanos=EXPECTED_USD_NANOS,
        attempt_reserved_usd_nanos=EXPECTED_USD_NANOS,
        attempt_settled_usd_nanos=EXPECTED_USD_NANOS,
        provider_reported_credit_micro_units=EXPECTED_PROVIDER_CREDIT_MICRO_UNITS,
        artifact_sha256="c" * 64,
        artifact_size_bytes=123,
    )
    serialized = reconcile_single_task_charge(result).model_dump_json()

    assert "prompt" not in serialized.lower()
    assert "http://" not in serialized
    assert "https://" not in serialized
    assert str(Path.home()) not in serialized


def stat_mode(path: Path) -> int:
    return os.stat(path).st_mode & 0o777


def test_builder_and_no_key_cli_preflight_are_fail_closed(tmp_path: Path) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    timestamp = now.isoformat().replace("+00:00", "Z")
    record = tmp_path / "cli-approval.json"
    builder = subprocess.run(
        [
            sys.executable,
            "scripts/build_w1_31_billing_approval.py",
            "--approval-id",
            "w1_31_cli_test_001",
            "--approved-by",
            "owner-fixture",
            "--confirmed-by",
            "operator-fixture",
            "--price-checked-at",
            timestamp,
            "--account-readiness-checked-at",
            timestamp,
            "--available-credit-micro-units",
            str(EXPECTED_PROVIDER_CREDIT_MICRO_UNITS),
            "--authorization-statement",
            AUTHORIZATION_STATEMENT,
            "--output",
            str(record),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert builder.returncode == 0
    assert stat_mode(record) == 0o600

    environment = dict(os.environ)
    environment.pop("POYO_API_KEY", None)
    preflight = subprocess.run(
        [
            sys.executable,
            "scripts/w1_31_provider_billing_reconciliation.py",
            "--approval-record",
            str(record),
            "--run-directory",
            str(tmp_path / "run"),
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    report = json.loads(preflight.stdout)
    assert preflight.returncode == 2
    assert report["blocked"] is True
    assert report["provider_call_allowed"] is False
    assert "POYO_API_KEY is absent" in preflight.stdout


def test_fresh_process_w1_31_config_import_never_calls_load_dotenv() -> None:
    script = """
import os
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
import dotenv
def forbidden(*args, **kwargs):
    raise AssertionError('load_dotenv must not be called')
dotenv.load_dotenv = forbidden
import src.config
print('config_imported_without_dotenv=1')
"""
    environment = dict(os.environ)
    environment["PYTHON_DOTENV_DISABLED"] = "1"
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "config_imported_without_dotenv=1"


@pytest.mark.asyncio
async def test_live_cli_is_retired_before_any_execution_callback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts import w1_31_provider_billing_reconciliation as cli

    now = datetime.now(UTC).replace(microsecond=0)
    payload = build_private_approval_payload(
        approval_id="w1_31_sqlite_failure_fixture_001",
        approved_by="owner-fixture",
        confirmed_by="operator-fixture",
        approved_at=(now - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
        expires_at=(now + timedelta(minutes=30)).isoformat().replace("+00:00", "Z"),
        price_checked_at=now.isoformat().replace("+00:00", "Z"),
        account_readiness_checked_at=now.isoformat().replace("+00:00", "Z"),
        available_credit_micro_units=EXPECTED_PROVIDER_CREDIT_MICRO_UNITS,
        authorization_statement=AUTHORIZATION_STATEMENT,
    )
    record_path = _write_record(tmp_path, payload)
    monkeypatch.setenv("POYO_API_KEY", "fixture-key")
    monkeypatch.setenv(cli.EXECUTE_ENV, "1")
    monkeypatch.setattr(
        cli,
        "_args",
        lambda: SimpleNamespace(
            approval_record=record_path,
            run_directory=tmp_path / "run",
            execute=True,
            pretty=False,
        ),
    )

    exit_code = await cli._main()
    captured = capsys.readouterr()

    assert exit_code == 2
    assert json.loads(captured.out) == {
        "status": "blocked",
        "reason": "w1_31_execution_retired",
        "provider_call_allowed": False,
    }
    assert captured.err == ""
    assert str(Path.home()) not in captured.out


def test_readback_cli_maps_corrupt_sqlite_to_safe_nonzero_json(tmp_path: Path) -> None:
    run_directory = tmp_path / "corrupt-ledger"
    run_directory.mkdir()
    (run_directory / "provider-cost-ledger.sqlite3").write_bytes(b"not-a-sqlite-database")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/read_w1_31_billing_ledger.py",
            "--run-directory",
            str(run_directory),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert json.loads(result.stdout) == {
        "status": "blocked",
        "reason": "w1_31_ledger_readback_failed",
    }
    assert result.stderr == ""
    assert str(Path.home()) not in result.stdout


class _FixtureResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.status_code = 200
        self._payload = payload
        self.content = json.dumps(payload).encode()
        self.text = self.content.decode()

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        return None


class _FixturePoyoClient:
    posts = 0
    gets = 0

    def __init__(self, **_: Any) -> None:
        pass

    async def post(self, path: str, **_: Any) -> _FixtureResponse:
        assert path == "/api/generate/submit"
        type(self).posts += 1
        return _FixtureResponse(
            {"code": 200, "data": {"task_id": "task_w131_fixture", "status": "queued"}}
        )

    async def get(self, path: str, **_: Any) -> _FixtureResponse:
        assert path == "/api/generate/status/task_w131_fixture"
        type(self).gets += 1
        return _FixtureResponse(
            {
                "code": 200,
                "data": {
                    "status": "finished",
                    "credits_amount": EXPECTED_PROVIDER_CREDIT_MICRO_UNITS,
                    "files": [{"file_url": "https://93.184.216.34/w131.png"}],
                },
            }
        )

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_canonical_sample_is_retired_before_provider_client_construction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.tools import poyo_client as poyo_module

    now = datetime.now(UTC).replace(microsecond=0)
    payload = build_private_approval_payload(
        approval_id="w1_31_fixture_current_001",
        approved_by="owner-pray",
        confirmed_by="operator-alice",
        approved_at=(now - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
        expires_at=(now + timedelta(minutes=30)).isoformat().replace("+00:00", "Z"),
        price_checked_at=now.isoformat().replace("+00:00", "Z"),
        account_readiness_checked_at=now.isoformat().replace("+00:00", "Z"),
        available_credit_micro_units=EXPECTED_PROVIDER_CREDIT_MICRO_UNITS,
        authorization_statement=AUTHORIZATION_STATEMENT,
    )
    record = parse_private_approval_record(_write_record(tmp_path, payload), now=now)
    _FixturePoyoClient.posts = 0
    _FixturePoyoClient.gets = 0
    monkeypatch.setattr(poyo_module.httpx, "AsyncClient", _FixturePoyoClient)

    with pytest.raises(RuntimeError, match="w1_31_execution_retired"):
        await execute_canonical_w131_sample(
            record=record,
            run_directory=tmp_path / "run",
            env={"POYO_API_KEY": "fixture-key-never-sent"},
        )

    assert _FixturePoyoClient.posts == 0
    assert _FixturePoyoClient.gets == 0
    assert not (tmp_path / "run").exists()
