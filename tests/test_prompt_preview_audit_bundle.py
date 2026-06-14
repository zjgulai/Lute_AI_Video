from __future__ import annotations

import json

from src.models.commercial_contracts import QualityContract
from src.pipeline.runtime_prompt_preview import RuntimePromptInjectionDiff, RuntimePromptPreviewResult
from src.quality.prompt_preview_audit_bundle import build_prompt_preview_audit_bundle


def test_prompt_preview_audit_bundle_keeps_allowed_preview_evidence_bounded():
    bundle = build_prompt_preview_audit_bundle(
        contract=_quality_contract(),
        preview=_preview(prompt_preview_allowed=True, compile_blocked=False),
    )
    payload = bundle.model_dump(mode="json")

    assert bundle.evidence_boundary.decision == "allowed-with-label"
    assert bundle.evidence_boundary.evidence_level == "L2-fixture-or-dry-run"
    assert bundle.gate_decision.status == "review_required"
    assert bundle.delivery_accepted is False
    assert bundle.publish_allowed is False
    assert "dry-run prompt preview produced an auditable prompt hash" in bundle.evidence_boundary.supported_claims
    assert "delivery accepted" in bundle.evidence_boundary.forbidden_claims
    assert "provider job submitted" in bundle.evidence_boundary.forbidden_claims
    assert payload["prompt_hash"] == "sha256:prompt_preview_fixture"

    serialized = json.dumps(payload)
    assert "prompt body must not leak" not in serialized
    assert "must-not-leak" not in serialized
    assert "prompt" not in payload["preview"]


def test_prompt_preview_audit_bundle_blocks_and_carries_repair_plan():
    bundle = build_prompt_preview_audit_bundle(
        contract=_quality_contract(),
        preview=_preview(
            prompt_preview_allowed=False,
            compile_blocked=True,
            prompt_hash=None,
            block_reasons=["runtime injection is not allowed", "reviewed brand bundle missing"],
        ),
    )

    assert bundle.evidence_boundary.decision == "blocked"
    assert bundle.gate_decision.status == "blocked"
    assert bundle.prompt_hash is None
    assert bundle.repair_plan.actions[0].check == "runtime_prompt_preview_allowed"
    assert "blocking reasons and repair actions are available" in bundle.evidence_boundary.supported_claims
    assert "commercial production ready" in bundle.evidence_boundary.forbidden_claims


def test_prompt_preview_audit_bundle_marks_token_diff_as_blocked_not_delivery_ready():
    bundle = build_prompt_preview_audit_bundle(
        contract=_quality_contract(),
        preview=_preview(
            prompt_preview_allowed=False,
            compile_blocked=True,
            prompt_hash=None,
            block_reasons=["runtime injection token ids do not match compile bundle"],
            injection_diff=RuntimePromptInjectionDiff(
                runtime_hard_token_ids=["bat_runtime"],
                compile_hard_token_ids=["bat_compile"],
                missing_runtime_hard_token_ids=["bat_compile"],
                compile_extra_hard_token_ids=["bat_runtime"],
            ),
        ),
    )

    assert bundle.evidence_boundary.decision == "blocked"
    assert bundle.gate_decision.publish_allowed is False
    assert [action.check for action in bundle.repair_plan.actions] == [
        "runtime_prompt_preview_allowed",
        "runtime_prompt_injection_diff_pass",
    ]
    assert "repair blocker checks and rerun dry-run prompt preview audit" in bundle.evidence_boundary.next_evidence


def _quality_contract() -> QualityContract:
    return QualityContract(
        contract_id="qc_s1_prompt_preview_fixture",
        scenario="s1",
        stage="prompt_preview",
        platform="tiktok",
        brand_id="momcozy",
    )


def _preview(
    *,
    prompt_preview_allowed: bool,
    compile_blocked: bool,
    prompt_hash: str | None = "sha256:prompt_preview_fixture",
    block_reasons: list[str] | None = None,
    injection_diff: RuntimePromptInjectionDiff | None = None,
) -> RuntimePromptPreviewResult:
    return RuntimePromptPreviewResult(
        compile_id="pci_fixture",
        scenario="s1",
        step="video_prompts",
        provider="poyo",
        model="seedance-2",
        prompt_preview_allowed=prompt_preview_allowed,
        compile_blocked=compile_blocked,
        prompt_hash=prompt_hash,
        duration_seconds=5,
        aspect_ratio="9:16",
        hard_token_ids=["bat_hard_fixture"],
        block_reasons=block_reasons or [],
        injection_diff=injection_diff or RuntimePromptInjectionDiff(
            runtime_hard_token_ids=["bat_hard_fixture"],
            compile_hard_token_ids=["bat_hard_fixture"],
        ),
    )
