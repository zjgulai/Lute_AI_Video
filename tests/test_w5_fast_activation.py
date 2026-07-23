from __future__ import annotations

import ast
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "src" / "pipeline" / "w5_fast_activation.py"
AUTHORIZATION_STATEMENT = (
    "I authorize exactly one W5 Fast provider submission bound to this plan; "
    "retry, publish, and delivery remain disabled."
)


def _times() -> tuple[datetime, datetime, datetime]:
    created_at = datetime(2026, 7, 23, 8, 0, tzinfo=UTC)
    return created_at, created_at + timedelta(hours=2), created_at + timedelta(hours=1)


def _plan(*, with_tts: bool = False) -> Any:
    from src.pipeline.w5_acceptance_harness import build_w5_plan_draft

    created_at, expires_at, _ = _times()
    caps = {"llm": 1, "video": 1}
    if with_tts:
        caps["tts"] = 1
    return build_w5_plan_draft(
        scenario="fast",
        tenant_id="tenant-alpha",
        sample_ref="sample:fast:001",
        budget_limit_usd_nanos=25_000_000,
        provider_job_caps=caps,
        selected_optional_media=("tts_audio",) if with_tts else (),
        created_at=created_at,
        expires_at=expires_at,
    )


def _activation_payload(plan: Any, **changes: Any) -> dict[str, Any]:
    created_at, _, _ = _times()
    payload: dict[str, Any] = {
        "version": "w5-fast-activation.v1",
        "scope": "w5-fast-activation",
        "activation_id": "w5fastact:fixture-001",
        "plan_id": plan.plan_id,
        "tenant_id": plan.tenant_id,
        "scenario": "fast",
        "sample_ref": plan.sample_ref,
        "approved_by": "reviewer:ll",
        "approved_at": (created_at + timedelta(minutes=30)).isoformat(),
        "expires_at": (created_at + timedelta(hours=1, minutes=30)).isoformat(),
        "authorization_statement": AUTHORIZATION_STATEMENT,
        "template_only": False,
        "budget_limit_usd_nanos": plan.budget_limit_usd_nanos,
        "selected_optional_media": list(plan.selected_optional_media),
        "provider_job_caps": dict(plan.provider_job_caps),
        "submission_cap": 1,
        "automatic_retry_cap": 0,
        "provider_max_retries": 0,
        "artifact_disposition": "pending_review",
        "provider_mutation_approved": True,
        "runtime_binding_required": True,
        "publish_allowed": False,
        "delivery_accepted": False,
    }
    payload.update(changes)
    return payload


def _validate(plan: Any, payload: dict[str, Any], *, now: datetime | None = None) -> Any:
    from src.pipeline.w5_fast_activation import validate_w5_fast_activation_json

    _, _, default_now = _times()
    return validate_w5_fast_activation_json(
        json.dumps(payload),
        plan=plan,
        now=now or default_now,
    )


def test_exact_fast_activation_binds_plan_without_runtime_authority() -> None:
    plan = _plan()

    activation = _validate(plan, _activation_payload(plan))

    assert activation.plan_id == plan.plan_id
    assert activation.tenant_id == plan.tenant_id
    assert activation.sample_ref == plan.sample_ref
    assert dict(activation.provider_job_caps) == {"llm": 1, "video": 1}
    assert activation.provider_mutation_approved is True
    assert activation.runtime_binding_required is True
    assert activation.publish_allowed is False
    assert activation.delivery_accepted is False


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("plan_id", "w5plan:00000000000000000000000000000000", "plan"),
        ("tenant_id", "tenant-other", "tenant"),
        ("sample_ref", "sample:fast:other", "sample"),
        ("scenario", "s1", "scenario"),
        ("budget_limit_usd_nanos", 25_000_001, "budget"),
        ("provider_job_caps", {"llm": 1, "video": 2}, "job cap"),
        ("selected_optional_media", ["tts_audio"], "optional media"),
        ("authorization_statement", "approved", "authorization_statement"),
        ("submission_cap", 2, "submission_cap"),
        ("automatic_retry_cap", 1, "automatic_retry_cap"),
        ("provider_max_retries", 1, "provider_max_retries"),
        ("artifact_disposition", "quarantine", "artifact_disposition"),
        ("provider_mutation_approved", False, "provider_mutation_approved"),
        ("runtime_binding_required", False, "runtime_binding_required"),
        ("publish_allowed", True, "publish_allowed"),
        ("delivery_accepted", True, "delivery_accepted"),
    ),
)
def test_activation_rejects_scope_authority_or_plan_tamper(
    field: str,
    value: object,
    message: str,
) -> None:
    plan = _plan()

    with pytest.raises((ValueError, ValidationError), match=message):
        _validate(plan, _activation_payload(plan, **{field: value}))


def test_tts_activation_requires_exact_optional_choice_and_cap() -> None:
    plan = _plan(with_tts=True)
    activation = _validate(plan, _activation_payload(plan))

    assert activation.selected_optional_media == ("tts_audio",)
    assert dict(activation.provider_job_caps) == {"llm": 1, "video": 1, "tts": 1}


@pytest.mark.parametrize(
    "raw_transform",
    (
        lambda raw: raw.replace(
            '"provider_job_caps": {"llm": 1, "video": 1}',
            '"provider_job_caps": {"llm": 1, "llm": 1, "video": 1}',
        ),
        lambda raw: raw.replace('"budget_limit_usd_nanos": 25000000', '"budget_limit_usd_nanos": 1.5'),
        lambda raw: raw.replace('"budget_limit_usd_nanos": 25000000', '"budget_limit_usd_nanos": NaN'),
        lambda raw: raw[:-1] + ', "unknown": true}',
    ),
)
def test_activation_original_json_rejects_duplicate_float_nonfinite_or_unknown(
    raw_transform: Any,
) -> None:
    from src.pipeline.w5_fast_activation import validate_w5_fast_activation_json

    plan = _plan()
    raw = json.dumps(_activation_payload(plan))

    with pytest.raises((ValueError, ValidationError)):
        validate_w5_fast_activation_json(
            raw_transform(raw),
            plan=plan,
            now=_times()[2],
        )


def test_activation_original_json_limit_is_measured_in_utf8_bytes() -> None:
    from src.pipeline.w5_fast_activation import validate_w5_fast_activation_json

    with pytest.raises(ValueError, match="bounded original JSON"):
        validate_w5_fast_activation_json(
            '"' + ("é" * 40_000) + '"',
            plan=_plan(),
            now=_times()[2],
        )


@pytest.mark.parametrize(
    ("approved_delta", "expiry_delta", "now_delta", "message"),
    (
        (timedelta(seconds=-1), timedelta(hours=1), timedelta(minutes=30), "plan creation"),
        (timedelta(hours=1, minutes=1), timedelta(hours=1, minutes=30), timedelta(hours=1), "future"),
        (timedelta(minutes=30), timedelta(hours=2, seconds=1), timedelta(hours=1), "plan expiry"),
        (timedelta(minutes=30), timedelta(hours=1), timedelta(hours=1), "expired"),
        (timedelta(minutes=30), timedelta(hours=3), timedelta(hours=1), "lifetime"),
    ),
)
def test_activation_rejects_invalid_time_boundaries(
    approved_delta: timedelta,
    expiry_delta: timedelta,
    now_delta: timedelta,
    message: str,
) -> None:
    plan = _plan()
    created_at = plan.created_at

    with pytest.raises(ValueError, match=message):
        _validate(
            plan,
            _activation_payload(
                plan,
                approved_at=(created_at + approved_delta).isoformat(),
                expires_at=(created_at + expiry_delta).isoformat(),
            ),
            now=created_at + now_delta,
        )


def test_activation_rejects_naive_validation_time() -> None:
    plan = _plan()

    with pytest.raises(ValueError, match="validation time"):
        _validate(
            plan,
            _activation_payload(plan),
            now=_times()[2].replace(tzinfo=None),
        )


def test_file_loader_requires_private_paths_and_rejects_symlink_escape(
    tmp_path: Path,
) -> None:
    from src.pipeline.w5_fast_activation import load_w5_fast_activation_files

    plan = _plan()
    plan_path = tmp_path / "plan.json"
    activation_path = tmp_path / "activation.json"
    plan_path.write_text(plan.model_dump_json())
    activation_path.write_text(json.dumps(_activation_payload(plan)))

    loaded_plan, loaded_activation = load_w5_fast_activation_files(
        plan_path=plan_path,
        activation_path=activation_path,
        now=_times()[2],
    )
    assert loaded_plan == plan
    assert loaded_activation.plan_id == plan.plan_id

    tracked_plan = REPO_ROOT / "docs" / "w5-fast-plan.json"
    with pytest.raises(ValueError, match="private"):
        load_w5_fast_activation_files(
            plan_path=tracked_plan,
            activation_path=activation_path,
            now=_times()[2],
        )

    symlink = tmp_path / "tracked-plan-link.json"
    symlink.symlink_to(REPO_ROOT / "README.md")
    with pytest.raises(ValueError, match="private"):
        load_w5_fast_activation_files(
            plan_path=symlink,
            activation_path=activation_path,
            now=_times()[2],
        )


def test_file_loader_rejects_oversized_regular_file_before_json_parsing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.pipeline.w5_fast_activation import load_w5_fast_activation_files

    oversized_plan = tmp_path / "oversized-plan.json"
    oversized_plan.write_bytes(b"x" * 64_001)
    activation_path = tmp_path / "activation.json"
    activation_path.write_text("{}")

    def reject_unbounded_read_bytes(_path: Path) -> bytes:
        raise AssertionError("unbounded Path.read_bytes() must not be used")

    monkeypatch.setattr(Path, "read_bytes", reject_unbounded_read_bytes)

    with pytest.raises(ValueError, match="size limit"):
        load_w5_fast_activation_files(
            plan_path=oversized_plan,
            activation_path=activation_path,
            now=_times()[2],
        )


def test_file_loader_rejects_non_regular_input_without_reading_it(
    tmp_path: Path,
) -> None:
    from src.pipeline.w5_fast_activation import load_w5_fast_activation_files

    non_regular_plan = tmp_path / "plan-directory"
    non_regular_plan.mkdir()
    activation_path = tmp_path / "activation.json"
    activation_path.write_text("{}")

    with pytest.raises(ValueError, match="regular file"):
        load_w5_fast_activation_files(
            plan_path=non_regular_plan,
            activation_path=activation_path,
            now=_times()[2],
        )


def test_readiness_report_can_pass_binding_but_never_authorizes_execution(
    tmp_path: Path,
) -> None:
    from src.pipeline.w5_fast_activation import build_w5_fast_readiness_report

    plan = _plan()
    plan_path = tmp_path / "plan.json"
    activation_path = tmp_path / "activation.json"
    plan_path.write_text(plan.model_dump_json())
    activation_path.write_text(json.dumps(_activation_payload(plan)))

    report = build_w5_fast_readiness_report(
        plan_path=plan_path,
        activation_path=activation_path,
        now=_times()[2],
    )

    assert report.status == "ready_for_private_binding"
    assert report.ready_for_private_binding is True
    assert report.provider_call_allowed is False
    assert report.execution_authorized is False
    assert report.publish_allowed is False
    assert report.delivery_accepted is False
    assert all(check.status == "pass" for check in report.checks)


def test_readiness_report_blocks_invalid_inputs_without_host_path_or_payload(
    tmp_path: Path,
) -> None:
    from src.pipeline.w5_fast_activation import build_w5_fast_readiness_report

    missing_plan = tmp_path / "private-secret-plan.json"
    missing_activation = tmp_path / "private-secret-activation.json"
    report = build_w5_fast_readiness_report(
        plan_path=missing_plan,
        activation_path=missing_activation,
        now=_times()[2],
    )
    payload = report.model_dump_json()

    assert report.status == "blocked"
    assert report.ready_for_private_binding is False
    assert report.provider_call_allowed is False
    assert str(tmp_path) not in payload
    assert "private-secret" not in payload


def test_readiness_report_blocks_bounded_deep_json_without_recursion_escape(
    tmp_path: Path,
) -> None:
    from src.pipeline.w5_fast_activation import build_w5_fast_readiness_report

    plan_path = tmp_path / "deep-plan.json"
    activation_path = tmp_path / "activation.json"
    plan_path.write_text(("[" * 15_000) + "0" + ("]" * 15_000))
    activation_path.write_text("{}")

    report = build_w5_fast_readiness_report(
        plan_path=plan_path,
        activation_path=activation_path,
        now=_times()[2],
    )

    assert report.status == "blocked"
    assert report.ready_for_private_binding is False
    assert report.provider_call_allowed is False


def test_activation_module_has_no_env_network_provider_database_or_execute_surface() -> None:
    tree = ast.parse(MODULE_PATH.read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    forbidden = (
        "requests",
        "httpx",
        "urllib",
        "services.provider_execution",
        "services.provider_cost",
        "storage",
        "routers",
    )
    assert not any(fragment in module for module in imported for fragment in forbidden)
    source = MODULE_PATH.read_text()
    assert "os.environ" not in source
    assert "provider_call_allowed=True" not in source
    assert "execution_authorized=True" not in source
