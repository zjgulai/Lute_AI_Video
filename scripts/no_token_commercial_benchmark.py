#!/usr/bin/env python3
"""Build a repeatable no-token commercial AI video 2.0 benchmark report."""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parents[1]
TOKEN_VAULT_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "commercial_video" / "momcozy_token_vault_minimal.json"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

with contextlib.redirect_stdout(sys.stderr):
    from src.models.commercial_contracts import (
        AllowedUse,
        AuditEvidenceBundle,
        BrandAssetToken,
        BrandConstraintBundle,
        CapabilityValue,
        CompileOptions,
        EditDecision,
        EditDecisionList,
        LicenseStatus,
        LongformProductionContract,
        MediaJobSpec,
        PlatformTarget,
        PromptCompileInput,
        ProviderCapability,
        QualityContract,
        SceneLedger,
        ShotLedger,
        StoryboardShotSchema,
        TimelineBlock,
        TimelineManifest,
        TokenReview,
        TokenStatus,
        TokenStrength,
    )
    from src.pipeline.brand_review_audit_bundle import build_brand_review_audit_bundle
    from src.pipeline.brand_token_intake import build_candidate_ledger_from_token_vault
    from src.pipeline.longform_audit_bundle import build_longform_audit_bundle
    from src.pipeline.production_job_ledger import ProductionJobLedger
    from src.pipeline.prompt_preview_audit_workflow import build_prompt_preview_audit_workflow
    from src.pipeline.runtime_injection_executor import (
        RuntimeInjectionResult,
        build_runtime_injection_result,
        find_reviewed_brand_bundle,
        with_reviewed_brand_bundles,
    )
    from src.quality.commercial_gate import evaluate_quality_contract


class BenchmarkCheck(BaseModel):
    name: str
    status: Literal["pass", "blocked", "review_required", "prepared"]
    detail: str
    evidence_refs: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)


class NoTokenCommercialBenchmarkReport(BaseModel):
    benchmark_id: str
    evidence_level: Literal["L2-fixture-or-dry-run"] = "L2-fixture-or-dry-run"
    provider_calls_made: bool = False
    authorized_live: bool = False
    checks: list[BenchmarkCheck] = Field(default_factory=list)
    blocked_count: int = 0
    review_required_count: int = 0
    forbidden_claims: list[str] = Field(default_factory=list)
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


def build_no_token_commercial_benchmark_report() -> NoTokenCommercialBenchmarkReport:
    """Run fixture/dry-run checks without reading provider tokens or calling providers."""
    checks = [
        _brand_review_check(),
        _runtime_injection_check(),
        _prompt_preview_check(),
        _quality_gate_check(),
        _production_job_ledger_check(),
        _longform_audit_check(),
    ]
    forbidden_claims = sorted({
        claim
        for check in checks
        for claim in check.forbidden_claims
    })
    return NoTokenCommercialBenchmarkReport(
        benchmark_id=f"no_token_commercial_benchmark_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        checks=checks,
        blocked_count=sum(1 for check in checks if check.status == "blocked"),
        review_required_count=sum(1 for check in checks if check.status == "review_required"),
        forbidden_claims=forbidden_claims,
    )


def _brand_review_check() -> BenchmarkCheck:
    ledger = build_candidate_ledger_from_token_vault(TOKEN_VAULT_FIXTURE).ledger
    bundle = build_brand_review_audit_bundle(ledger)
    return BenchmarkCheck(
        name="brand_review_candidate_only",
        status="blocked" if not bundle.approved_for_runtime_injection else "pass",
        detail="candidate ledger remains blocked until explicit brand review decisions exist",
        evidence_refs=[bundle.audit_bundle_id, *bundle.skipped_token_ids[:3]],
        forbidden_claims=bundle.forbidden_claims,
    )


def _runtime_injection_check() -> BenchmarkCheck:
    reviewed_bundle = _reviewed_bundle("s1", "video_prompts")
    planned = {
        "scenario": "s1",
        "step": "video_prompts",
        "bundle_refs": ["BrandConstraintBundle"],
        "toolbox_refs": ["PromptPreviewToolbox"],
        "contract_refs": ["QualityContract"],
        "gate_checks": ["hard_brand_token_pass"],
    }
    result = build_runtime_injection_result(
        planned_injection=planned,
        bundle_lookup=find_reviewed_brand_bundle(
            config=with_reviewed_brand_bundles({}, [reviewed_bundle]),
            scenario="s1",
            step="video_prompts",
        ),
    )
    return BenchmarkCheck(
        name="runtime_injection_reviewed_bundle",
        status="pass" if result.prompt_injection_allowed else "blocked",
        detail="reviewed fixture bundle is accepted by runtime injection dry-run",
        evidence_refs=[result.brand_bundle_id or "missing_bundle", *result.source_token_ids],
        forbidden_claims=["provider job submitted", "delivery accepted", "publish allowed"],
    )


def _prompt_preview_check() -> BenchmarkCheck:
    runtime = RuntimeInjectionResult(
        scenario="s1",
        step="video_prompts",
        prompt_injection_allowed=True,
        brand_bundle_id="bundle_s1_video_prompts",
        hard_token_ids=["bat_s1_video_prompts_hard"],
        source_token_ids=["bat_s1_video_prompts_hard"],
    )
    bundle = build_prompt_preview_audit_workflow(
        contract=QualityContract(
            contract_id="qc_benchmark_prompt_preview",
            scenario="s1",
            stage="prompt_preview",
            platform="tiktok",
            brand_id="momcozy",
        ),
        compile_input=_compile_input(_reviewed_bundle("s1", "video_prompts")),
        runtime_injection=runtime,
        planned_injection={"hard_token_ids": ["bat_s1_video_prompts_hard"], "soft_token_ids": []},
    )
    return BenchmarkCheck(
        name="prompt_preview_audit",
        status=bundle.gate_decision.status,
        detail="sanitized prompt preview bundle remains evidence-bounded",
        evidence_refs=[bundle.audit_bundle_id, bundle.prompt_hash or "missing_prompt_hash"],
        forbidden_claims=bundle.evidence_boundary.forbidden_claims,
    )


def _quality_gate_check() -> BenchmarkCheck:
    result = evaluate_quality_contract(
        QualityContract(
            contract_id="qc_benchmark_final_video",
            scenario="s1",
            stage="final_video",
            platform="tiktok",
            brand_id="momcozy",
            blocking_checks=["rights_pass", "claim_substantiation_pass", "media_file_exists"],
            required_evidence=["rights_evidence_refs", "claim_evidence_refs", "artifact_manifest_id"],
        ),
        AuditEvidenceBundle(
            evidence_bundle_id="aeb_benchmark_final_video",
            scenario="s1",
            stage="final_video",
            brand_bundle_id="bundle_s1_video_prompts",
            source_token_ids=["bat_s1_video_prompts_hard"],
            artifact_manifest_id="artifact_benchmark_fixture",
            artifact_paths={"final_video": "fixture://final.mp4"},
            rights_evidence_refs=["rights_benchmark_fixture"],
            claim_evidence_refs=["claim_benchmark_fixture"],
            platform_target=PlatformTarget(platform="tiktok"),
        ),
    )
    return BenchmarkCheck(
        name="commercial_quality_gate",
        status=result.gate_decision.status,
        detail="fixture final-video gate passes blockers but requires human review",
        evidence_refs=[result.audit_id, result.gate_decision.decision_id],
        forbidden_claims=["delivery accepted", "publish allowed", "commercial production ready"],
    )


def _production_job_ledger_check() -> BenchmarkCheck:
    record = ProductionJobLedger().prepare(MediaJobSpec(
        job_id="benchmark_job_fixture",
        provider="poyo",
        model="seedance-2",
        scenario="s1",
        step_name="video_prompts",
        prompt_hash="sha256:benchmark_fixture",
        prompt_compile_id="pci_benchmark_fixture",
        brand_bundle_id="bundle_s1_video_prompts",
    ))
    return BenchmarkCheck(
        name="production_job_ledger",
        status="prepared",
        detail="prepared job is not submitted, delivered, or publishable",
        evidence_refs=[record.job_id, record.status],
        forbidden_claims=["provider job submitted", "delivery accepted", "publish allowed"],
    )


def _longform_audit_check() -> BenchmarkCheck:
    bundle = build_longform_audit_bundle(
        longform_contract=_longform_contract("s4"),
        quality_contract=QualityContract(
            contract_id="qc_benchmark_longform",
            scenario="s4",
            stage="longform_delivery",
            platform="tiktok",
            brand_id="momcozy",
        ),
        evidence=AuditEvidenceBundle(
            evidence_bundle_id="aeb_benchmark_longform",
            scenario="s4",
            stage="longform_delivery",
            brand_bundle_id="bundle_s4_longform",
            source_token_ids=["bat_s4_longform"],
            artifact_manifest_id="artifact_longform_fixture",
            rights_evidence_refs=["rights_longform_fixture"],
            source_fingerprint_refs=["fingerprint_longform_fixture"],
            timeline_manifest_refs=["timeline_manifest_fixture"],
            edit_decision_list_refs=["edl_fixture"],
            caption_safe_zone_refs=["caption_safe_fixture"],
            platform_target=PlatformTarget(platform="tiktok", duration_seconds=120),
        ),
    )
    return BenchmarkCheck(
        name="longform_audit",
        status=bundle.gate_decision.status,
        detail="longform audit passes blockers but remains review-only",
        evidence_refs=[bundle.audit_bundle_id, bundle.gate_decision.decision_id],
        forbidden_claims=bundle.forbidden_claims,
    )


def _compile_input(bundle: BrandConstraintBundle) -> PromptCompileInput:
    return PromptCompileInput(
        compile_id="pci_benchmark_prompt_preview",
        scenario="s1",
        step_name="video_prompts",
        shot=StoryboardShotSchema(
            shot_id="shot_benchmark_001",
            scenario="s1",
            beat="product reveal",
            visual_description="Momcozy product reveal in warm soft light",
            motion_description="slow push-in",
            claim_evidence_refs=["claim_benchmark_fixture"],
        ),
        brand_bundle=bundle,
        provider_capability=ProviderCapability(
            capability_id="cap_benchmark_seedance",
            provider="poyo",
            model="seedance-2",
            model_family="seedance",
            supports_reference_images=CapabilityValue.SUPPORTED,
            supports_negative_prompt=CapabilityValue.SUPPORTED,
            max_duration_seconds=15,
        ),
        platform_target=PlatformTarget(platform="tiktok", aspect_ratio="9:16"),
        compile_options=CompileOptions(),
    )


def _reviewed_bundle(scenario: str, step: str) -> BrandConstraintBundle:
    return BrandConstraintBundle.build_approved(
        bundle_id=f"bundle_{scenario}_{step}",
        brand_id="momcozy",
        scenario=scenario,
        step=step,
        tokens=[
            _approved_token(
                token_id=f"bat_{scenario}_{step}_hard",
                scenario=scenario,
                step=step,
                strength=TokenStrength.HARD,
            )
        ],
    )


def _approved_token(
    *,
    token_id: str,
    scenario: str,
    step: str,
    strength: TokenStrength,
) -> BrandAssetToken:
    return BrandAssetToken(
        token_id=token_id,
        brand_id="momcozy",
        token_type="brand_voice",
        status=TokenStatus.APPROVED,
        strength=strength,
        payload={"raw": "must-not-leak"},
        payload_summary=["must-not-leak"],
        scenario_scope=[scenario],
        step_scope=[step],
        rights_ref="rights_benchmark_fixture",
        license_status=LicenseStatus.APPROVED,
        allowed_uses=[AllowedUse.GENERATION],
        review=TokenReview(review_status="approved", reviewed_by="benchmark_fixture"),
    )


def _longform_contract(scenario: str) -> LongformProductionContract:
    duration = 120
    return LongformProductionContract(
        contract_id=f"lfc_benchmark_{scenario}",
        scenario=scenario,
        brand_id="momcozy",
        target_duration_seconds=duration,
        scene_ledger=SceneLedger(
            scene_ledger_id=f"scene_benchmark_{scenario}",
            scenario=scenario,
            scene_ids=["scene_001", "scene_002"],
            narrative_beats=["setup", "payoff"],
            target_duration_seconds=duration,
        ),
        timeline_manifest=TimelineManifest(
            timeline_manifest_id=f"timeline_benchmark_{scenario}",
            scenario=scenario,
            duration_seconds=duration,
            timeline_blocks=[
                TimelineBlock(block_id="block_001", start_seconds=0, end_seconds=60, scene_ref="scene_001"),
                TimelineBlock(block_id="block_002", start_seconds=60, end_seconds=120, scene_ref="scene_002"),
            ],
        ),
        shot_ledger=ShotLedger(
            shot_ledger_id=f"shots_benchmark_{scenario}",
            scenario=scenario,
            shots=[
                StoryboardShotSchema(
                    shot_id=f"shot_{index:03d}",
                    scenario=scenario,
                    beat=f"beat {index}",
                    visual_description="fixture longform shot",
                    duration_seconds=40,
                )
                for index in range(1, 4)
            ],
        ),
        edit_decision_list=EditDecisionList(
            edl_id="edl_benchmark_longform",
            source_timeline_manifest_id=f"timeline_benchmark_{scenario}",
            decisions=[
                EditDecision(edit_id="edit_001", source_block_id="block_001", action="keep")
            ],
        ),
        review_checkpoint_ids=["review_longform_benchmark"],
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    report = build_no_token_commercial_benchmark_report()
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
