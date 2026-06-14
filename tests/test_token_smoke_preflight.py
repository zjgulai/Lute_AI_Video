from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from src.pipeline.token_smoke_preflight import (
    ACCOUNT_READINESS_RECORD_ENV,
    ACCOUNT_READINESS_SCOPE,
    APPROVAL_RECORD_ENV,
    APPROVAL_SCOPE,
    APPROVAL_STATEMENT_TEMPLATE,
    DEFAULT_AUTH_BUDGET_LIMIT,
    DEFAULT_AUTH_BUDGET_LIMIT_USD,
    DEFAULT_AUTH_MODEL,
    DEFAULT_AUTH_PROVIDER,
    DEFAULT_AUTH_PROVIDER_MODEL_SCOPE,
    DEFAULT_AUTH_TEST_SCOPE,
    PROVIDER_REVALIDATION_PATH,
    PROVIDER_REVALIDATION_REF,
    REQUIRED_API_KEY_ENVS,
    RUN_TOKEN_SMOKE_ENV,
    SAMPLE_PLAN_PATH,
    SAMPLE_PLAN_REF,
    build_provider_account_readiness_payload,
    build_token_smoke_preflight_report,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "commercial_token_smoke_preflight.py"


def test_missing_approval_record_blocks_even_when_token_flag_and_keys_are_set():
    env = _ready_env()

    report = build_token_smoke_preflight_report(env=env)

    assert report.blocked is True
    assert report.provider_call_allowed is False
    assert _check_status(report, "authorized_live_approval") == "block"
    assert report.evidence_level == "L2-fixture-or-dry-run"


def test_explicit_empty_env_does_not_fall_back_to_process_env(monkeypatch):
    monkeypatch.setenv(RUN_TOKEN_SMOKE_ENV, "1")
    for key_name in REQUIRED_API_KEY_ENVS:
        monkeypatch.setenv(key_name, f"sk_fixture_secret_{key_name.lower()}")

    report = build_token_smoke_preflight_report(env={})

    assert report.run_token_smoke is False
    assert report.provider_call_allowed is False
    assert _check_status(report, "run_token_smoke") == "block"
    assert all(_check_status(report, f"api_key:{key_name}") == "block" for key_name in REQUIRED_API_KEY_ENVS)
    assert "sk_fixture_secret" not in report.model_dump_json()


def test_missing_run_token_smoke_blocks_even_with_valid_approval_record(tmp_path: Path):
    approval_record = _write_approval_record(tmp_path)
    account_readiness = _write_account_readiness_record(tmp_path)
    env = _ready_env()
    env[RUN_TOKEN_SMOKE_ENV] = "0"
    env[APPROVAL_RECORD_ENV] = str(approval_record)
    env[ACCOUNT_READINESS_RECORD_ENV] = str(account_readiness)

    report = build_token_smoke_preflight_report(env=env)

    assert report.blocked is True
    assert report.provider_call_allowed is False
    assert _check_status(report, "run_token_smoke") == "block"


def test_valid_preflight_allows_harness_entry_without_provider_call(tmp_path: Path):
    approval_record = _write_approval_record(tmp_path)
    account_readiness = _write_account_readiness_record(tmp_path)
    env = _ready_env()
    env[APPROVAL_RECORD_ENV] = str(approval_record)
    env[ACCOUNT_READINESS_RECORD_ENV] = str(account_readiness)

    report = build_token_smoke_preflight_report(env=env)

    assert report.blocked is False
    assert report.provider_call_allowed is True
    assert report.account_readiness_record_ref == str(account_readiness)
    assert report.provider_revalidation_ref == PROVIDER_REVALIDATION_REF
    assert report.sample_plan_ref == SAMPLE_PLAN_REF
    assert report.approved_provider == "poyo"
    assert report.approved_model == "seedance-2"
    assert report.approved_provider_model_scope == DEFAULT_AUTH_PROVIDER_MODEL_SCOPE
    assert report.approved_test_scope == DEFAULT_AUTH_TEST_SCOPE
    assert report.approved_budget_limit_usd == 3.0
    assert report.approved_max_sample_count == 4
    assert report.approved_max_provider_calls == 4
    assert report.approved_max_total_cost_usd == 3.0
    assert report.approved_per_job_cost_ceiling_usd == 2.5
    assert report.approved_max_retry_count == 0
    assert {check.status for check in report.checks} == {"pass"}
    assert "sk_fixture_secret" not in report.model_dump_json()


def test_provider_capability_evidence_requires_current_revalidation_ref(tmp_path: Path):
    approval_record = _write_approval_record(
        tmp_path,
        provider_revalidation_ref="configs/old-poyo-matrix.json",
    )
    env = _ready_env()
    env[APPROVAL_RECORD_ENV] = str(approval_record)

    report = build_token_smoke_preflight_report(env=env)

    assert report.blocked is True
    assert report.provider_call_allowed is False
    assert _check_status(report, "authorized_live_approval") == "pass"
    assert _check_status(report, "provider_capability_evidence") == "block"
    assert PROVIDER_REVALIDATION_REF in _check_detail(report, "provider_capability_evidence")


def test_sample_plan_contract_requires_current_ref(tmp_path: Path):
    approval_record = _write_approval_record(
        tmp_path,
        sample_plan_ref="configs/old-sample-plan.json",
    )
    env = _ready_env()
    env[APPROVAL_RECORD_ENV] = str(approval_record)

    report = build_token_smoke_preflight_report(env=env)

    assert report.blocked is True
    assert report.provider_call_allowed is False
    assert _check_status(report, "authorized_live_approval") == "pass"
    assert _check_status(report, "sample_plan_contract") == "block"
    assert SAMPLE_PLAN_REF in _check_detail(report, "sample_plan_contract")


def test_sample_plan_contract_blocks_over_budget_plan(tmp_path: Path):
    approval_record = _write_approval_record(
        tmp_path,
        sample_plan={
            "max_sample_count": 5,
            "max_provider_calls": 5,
            "scenarios": ["toolbox"],
            "toolbox_tool_ids": ["product-image"],
            "sample_ids": ["momcozy-sterilizer-main-45-gpt-image-2"],
            "asset_package": {
                "brand": "momcozy",
                "product": "sterilizer",
                "image_count": 3,
                "video_count": 1,
                "asset_status": "pending_review",
                "delivery_accepted": False,
                "publish_allowed": False,
                "approved_brand_token_write": False,
            },
            "s5_requires_separate_confirmation": True,
        },
    )
    env = _ready_env()
    env[APPROVAL_RECORD_ENV] = str(approval_record)

    report = build_token_smoke_preflight_report(env=env)

    assert report.blocked is True
    assert report.provider_call_allowed is False
    assert _check_status(report, "sample_plan_contract") == "block"
    assert "sample_plan.max_sample_count" in _check_detail(report, "sample_plan_contract")


def test_authorized_live_sample_plan_contract_keeps_no_token_budget_boundary():
    payload = json.loads(SAMPLE_PLAN_PATH.read_text())
    image_samples = {item["sample_id"]: item for item in payload["core_asset_samples"]}
    video_samples = {item["sample_id"]: item for item in payload["core_video_samples"]}

    assert payload["status"] == "stable"
    assert payload["evidence_level"] == "L2-fixture-or-dry-run"
    assert payload["no_provider_call"] is True
    assert payload["sample_plan_ref"] == SAMPLE_PLAN_REF
    assert payload["provider_revalidation_ref"] == PROVIDER_REVALIDATION_REF
    assert payload["provider_model_scope"] == DEFAULT_AUTH_PROVIDER_MODEL_SCOPE
    assert payload["test_scope"] == DEFAULT_AUTH_TEST_SCOPE
    assert payload["asset_review_status"] == "pending_review"
    assert payload["limits"]["max_sample_count"] == 4
    assert payload["limits"]["max_provider_calls"] == 4
    assert payload["limits"]["max_total_cost_usd"] == 3.0
    assert payload["limits"]["per_job_cost_ceiling_usd"] == 2.5
    assert payload["limits"]["max_retry_count"] == 0
    assert payload["stop_loss_policy"]["stop_on_first_failure"] is True
    assert payload["allowed_scenarios"] == ["toolbox"]
    assert "product-image" in payload["allowed_toolbox_tool_ids"]
    assert "ecommerce-visual" in payload["allowed_toolbox_tool_ids"]
    assert "storyboard" in payload["allowed_toolbox_tool_ids"]
    assert "digital-human" not in payload["allowed_toolbox_tool_ids"]
    assert "warm" not in json.dumps(payload["core_asset_samples"], ensure_ascii=False).lower()
    assert "warm" not in json.dumps(payload["core_video_samples"], ensure_ascii=False).lower()

    assert len(image_samples) == 3
    assert image_samples["momcozy-sterilizer-main-45-gpt-image-2"]["model"] == "gpt-image-2"
    assert image_samples["momcozy-sterilizer-uv-benefit-gpt-image-2"]["tool_id"] == "ecommerce-visual"
    video = video_samples["momcozy-sterilizer-i2v-15s-seedance-2"]
    assert video["workflow"] == "image-to-video"
    assert video["aspect_ratio"] == "9:16"
    assert video["duration_seconds"] == 15
    assert len(video["reference_asset_sample_ids"]) == 3


def test_poyo_current_revalidation_contract_keeps_public_doc_evidence_boundary():
    payload = json.loads(PROVIDER_REVALIDATION_PATH.read_text())
    models = {item["model"]: item for item in payload["models"]}

    assert payload["status"] == "stable"
    assert payload["evidence_level"] == "L1-public-doc-revalidation"
    assert payload["provider"] == "poyo"
    assert payload["no_provider_call"] is True
    assert "https://docs.poyo.ai/api-manual/overview" in payload["source_urls"]
    assert "https://poyo.ai/models/seedance-2" in payload["source_urls"]
    assert "https://poyo.ai/models/gpt-image-2" in payload["source_urls"]

    seedance = models["seedance-2"]
    assert "seedance-2-fast" in seedance["available_model_ids"]
    assert seedance["duration_seconds"] == {"min": 4, "max": 15}
    assert "1080p" in seedance["resolutions"]
    assert seedance["reference_limits"]["combined_max"] == 12
    assert seedance["pricing_usd"]["seedance_2_720p_text_or_image_to_video_per_second"] == 0.2
    assert seedance["recommended_l4_smoke_default"]["resolution"] == "480p"
    assert seedance["recommended_l4_smoke_default"]["estimated_provider_cost_usd"] == 0.4

    image = models["gpt-image-2"]
    assert "gpt-image-2-edit" in image["available_model_ids"]
    assert image["prompt_max_chars"] == 20000
    assert image["returns_per_request"] == 1
    assert image["pricing_usd"]["low_1k_per_generation"] == 0.01
    assert image["pricing_usd"]["high_4k_per_generation"] == 0.321


def test_approval_record_requires_exact_c21_statement_provider_model_and_budget(tmp_path: Path):
    approval_record = _write_approval_record(tmp_path, approval_statement="approved")
    env = _ready_env()
    env[APPROVAL_RECORD_ENV] = str(approval_record)

    report = build_token_smoke_preflight_report(env=env)

    assert report.blocked is True
    assert report.provider_call_allowed is False
    assert _check_status(report, "authorized_live_approval") == "block"
    assert "exact C21 user authorization statement" in _check_detail(report, "authorized_live_approval")


def test_provider_capability_evidence_is_bound_to_approved_provider_model(tmp_path: Path):
    provider = "unknown"
    model = "mystery-video-1"
    budget_limit = DEFAULT_AUTH_BUDGET_LIMIT
    approval_record = _write_approval_record(
        tmp_path,
        provider=provider,
        model=model,
        budget_limit=budget_limit,
        approval_statement=_approval_statement(DEFAULT_AUTH_PROVIDER_MODEL_SCOPE, DEFAULT_AUTH_TEST_SCOPE, budget_limit),
    )
    env = _ready_env()
    env[APPROVAL_RECORD_ENV] = str(approval_record)

    report = build_token_smoke_preflight_report(env=env)

    assert report.blocked is True
    assert report.provider_call_allowed is False
    assert _check_status(report, "authorized_live_approval") == "pass"
    assert _check_status(report, "provider_capability_evidence") == "block"
    assert "unknown/mystery-video-1" in _check_detail(report, "provider_capability_evidence")


def test_approval_record_blocks_non_finite_budget(tmp_path: Path):
    approval_record = _write_approval_record(tmp_path, budget_limit_usd="NaN")
    env = _ready_env()
    env[APPROVAL_RECORD_ENV] = str(approval_record)

    report = build_token_smoke_preflight_report(env=env)

    assert report.blocked is True
    assert report.provider_call_allowed is False
    assert _check_status(report, "authorized_live_approval") == "block"
    assert "budget_limit_usd must be a positive number" in _check_detail(report, "authorized_live_approval")


def test_approval_record_template_is_blocked_even_with_other_fields_present(tmp_path: Path):
    approval_record = _write_approval_record(tmp_path, template_only=True)
    env = _ready_env()
    env[APPROVAL_RECORD_ENV] = str(approval_record)

    report = build_token_smoke_preflight_report(env=env)

    assert report.blocked is True
    assert report.provider_call_allowed is False
    assert _check_status(report, "authorized_live_approval") == "block"
    assert "template_only must be false" in _check_detail(report, "authorized_live_approval")


def test_approval_record_requires_budget_stop_loss_fields(tmp_path: Path):
    approval_record = _write_approval_record(tmp_path, budget_stop_loss={})
    env = _ready_env()
    env[APPROVAL_RECORD_ENV] = str(approval_record)

    report = build_token_smoke_preflight_report(env=env)

    assert report.blocked is True
    assert report.provider_call_allowed is False
    assert _check_status(report, "budget_stop_loss") == "block"
    assert "budget_stop_loss.max_total_cost_usd" in _check_detail(report, "budget_stop_loss")


def test_approval_record_blocks_loose_retry_or_missing_halt_policy(tmp_path: Path):
    approval_record = _write_approval_record(
        tmp_path,
        budget_stop_loss={
            "max_total_cost_usd": 1.0,
            "per_job_cost_ceiling_usd": 0.5,
            "max_retry_count": 2,
            "stop_on_first_failure": True,
            "halt_on_rate_limit": True,
            "halt_on_quota_error": True,
            "halt_on_content_rejection": True,
            "halt_on_missing_artifact": True,
        },
    )
    env = _ready_env()
    env[APPROVAL_RECORD_ENV] = str(approval_record)

    report = build_token_smoke_preflight_report(env=env)

    assert report.blocked is True
    assert report.provider_call_allowed is False
    assert _check_status(report, "budget_stop_loss") == "block"
    assert "max_retry_count must be 0 or 1" in _check_detail(report, "budget_stop_loss")


def test_provider_account_readiness_record_is_required_for_valid_approval(tmp_path: Path):
    approval_record = _write_approval_record(tmp_path)
    env = _ready_env()
    env[APPROVAL_RECORD_ENV] = str(approval_record)

    report = build_token_smoke_preflight_report(env=env)

    assert report.blocked is True
    assert report.provider_call_allowed is False
    assert _check_status(report, "provider_account_readiness") == "block"
    assert ACCOUNT_READINESS_RECORD_ENV in _check_detail(report, "provider_account_readiness")


def test_provider_account_readiness_blocks_template_and_underfunded_records(tmp_path: Path):
    approval_record = _write_approval_record(tmp_path)
    template_record = _write_account_readiness_record(tmp_path, template_only=True)
    underfunded_record = _write_account_readiness_record(
        tmp_path,
        file_name="underfunded-account-readiness.json",
        available_credit_usd=2.99,
        minimum_required_credit_usd=3.0,
    )

    for record, expected in [
        (template_record, "template_only must be false"),
        (underfunded_record, "available_credit_usd must cover"),
    ]:
        env = _ready_env()
        env[APPROVAL_RECORD_ENV] = str(approval_record)
        env[ACCOUNT_READINESS_RECORD_ENV] = str(record)

        report = build_token_smoke_preflight_report(env=env)

        assert report.blocked is True
        assert report.provider_call_allowed is False
        assert _check_status(report, "provider_account_readiness") == "block"
        assert expected in _check_detail(report, "provider_account_readiness")


def test_provider_account_readiness_builder_keeps_secret_free_private_shape():
    payload = build_provider_account_readiness_payload(
        checked_by="pray",
        checked_at="2026-06-06T16:30:00Z",
        available_credit_usd=3.0,
    )

    assert payload["template_only"] is False
    assert payload["scope"] == ACCOUNT_READINESS_SCOPE
    assert payload["evidence_level"] == "L3-production-read-only"
    assert payload["no_provider_call"] is True
    assert payload["provider"] == "poyo"
    assert payload["provider_dashboard_balance_confirmed"] is True
    assert payload["api_key_configured_in_runtime_env"] is True
    assert payload["api_key_secret_not_recorded"] is True
    assert payload["available_credit_usd"] == 3.0
    assert payload["minimum_required_credit_usd"] == 3.0
    assert "API_KEY" not in json.dumps(payload)


def test_cli_exits_blocked_when_approval_is_missing():
    env = _ready_env()
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["blocked"] is True
    assert payload["provider_call_allowed"] is False
    assert "sk_fixture_secret" not in result.stdout


def _ready_env() -> dict[str, str]:
    env = {RUN_TOKEN_SMOKE_ENV: "1"}
    for key_name in REQUIRED_API_KEY_ENVS:
        env[key_name] = f"sk_fixture_secret_{key_name.lower()}"
    return env


def _write_approval_record(tmp_path: Path, **overrides) -> Path:
    path = tmp_path / "authorized-live-approval.json"
    provider = str(overrides.get("provider", DEFAULT_AUTH_PROVIDER))
    model = str(overrides.get("model", DEFAULT_AUTH_MODEL))
    provider_model_scope = str(overrides.get("provider_model_scope", DEFAULT_AUTH_PROVIDER_MODEL_SCOPE))
    test_scope = str(overrides.get("test_scope", DEFAULT_AUTH_TEST_SCOPE))
    budget_limit = str(overrides.get("budget_limit", DEFAULT_AUTH_BUDGET_LIMIT))
    payload = {
        "approval_id": "approval_fixture",
        "scope": APPROVAL_SCOPE,
        "evidence_level": "L4-authorized-live",
        "provider_calls_allowed": True,
        "approved_by": "user",
        "approved_at": "2026-06-04T00:00:00Z",
        "provider": provider,
        "model": model,
        "provider_model_scope": provider_model_scope,
        "test_scope": test_scope,
        "provider_revalidation_ref": PROVIDER_REVALIDATION_REF,
        "sample_plan_ref": SAMPLE_PLAN_REF,
        "budget_limit": budget_limit,
        "budget_limit_usd": DEFAULT_AUTH_BUDGET_LIMIT_USD,
        "sample_plan": {
            "max_sample_count": 4,
            "max_provider_calls": 4,
            "scenarios": ["toolbox"],
            "toolbox_tool_ids": ["product-image", "ecommerce-visual", "storyboard"],
            "sample_ids": [
                "momcozy-sterilizer-main-45-gpt-image-2",
                "momcozy-sterilizer-uv-benefit-gpt-image-2",
                "momcozy-sterilizer-kitchen-scene-gpt-image-2",
                "momcozy-sterilizer-i2v-15s-seedance-2",
            ],
            "asset_package": {
                "brand": "momcozy",
                "product": "sterilizer",
                "image_count": 3,
                "video_count": 1,
                "asset_status": "pending_review",
                "delivery_accepted": False,
                "publish_allowed": False,
                "approved_brand_token_write": False,
            },
            "s5_requires_separate_confirmation": True,
        },
        "budget_stop_loss": {
            "max_total_cost_usd": 3.0,
            "per_job_cost_ceiling_usd": 2.5,
            "max_retry_count": 0,
            "stop_on_first_failure": True,
            "halt_on_rate_limit": True,
            "halt_on_quota_error": True,
            "halt_on_content_rejection": True,
            "halt_on_missing_artifact": True,
        },
        "approval_statement": _approval_statement(provider_model_scope, test_scope, budget_limit),
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload, ensure_ascii=False))
    return path


def _write_account_readiness_record(tmp_path: Path, **overrides) -> Path:
    file_name = str(overrides.pop("file_name", "provider-account-readiness.json"))
    path = tmp_path / file_name
    payload = {
        "template_only": False,
        "readiness_id": "account_readiness_fixture",
        "scope": ACCOUNT_READINESS_SCOPE,
        "evidence_level": "L3-production-read-only",
        "no_provider_call": True,
        "provider": "poyo",
        "checked_by": "user",
        "checked_at": "2026-06-06T00:00:00Z",
        "provider_dashboard_balance_confirmed": True,
        "api_key_configured_in_runtime_env": True,
        "api_key_secret_not_recorded": True,
        "available_credit_usd": 3.0,
        "minimum_required_credit_usd": 3.0,
        "provider_revalidation_ref": PROVIDER_REVALIDATION_REF,
        "sample_plan_ref": SAMPLE_PLAN_REF,
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload, ensure_ascii=False))
    return path


def _approval_statement(provider_model_scope: str, test_scope: str, budget_limit: str) -> str:
    return APPROVAL_STATEMENT_TEMPLATE.format(
        provider_model_scope=provider_model_scope,
        test_scope=test_scope,
        budget_limit=budget_limit,
    )


def _check_status(report, name: str) -> str:
    for check in report.checks:
        if check.name == name:
            return check.status
    raise AssertionError(f"missing check {name}")


def _check_detail(report, name: str) -> str:
    for check in report.checks:
        if check.name == name:
            return check.detail
    raise AssertionError(f"missing check {name}")
