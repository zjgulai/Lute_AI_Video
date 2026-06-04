from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from src.models.commercial_contracts import (
    AllowedUse,
    BrandAssetToken,
    BrandConstraintBundle,
    CapabilityValue,
    CompileOptions,
    LicenseStatus,
    PlatformTarget,
    PromptCompileInput,
    ProviderCapability,
    QualityContract,
    StoryboardShotSchema,
    TokenReview,
    TokenStatus,
    TokenStrength,
)
from src.pipeline.runtime_injection_executor import RuntimeInjectionResult


@pytest.mark.asyncio
async def test_prompt_preview_audit_endpoint_returns_sanitized_l2_bundle(auth_headers) -> None:
    from src.api import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/scenario/s1/prompt-preview/audit",
            headers=auth_headers,
            json=_request_payload(),
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    serialized = json.dumps(payload)

    assert payload["evidence_boundary"]["evidence_level"] == "L2-fixture-or-dry-run"
    assert payload["evidence_boundary"]["decision"] == "allowed-with-label"
    assert payload["gate_decision"]["status"] == "review_required"
    assert payload["delivery_accepted"] is False
    assert payload["publish_allowed"] is False
    assert payload["prompt_hash"].startswith("sha256:")
    assert "must-not-leak" not in serialized
    assert "negative_prompt" not in serialized
    assert '"prompt"' not in serialized
    assert "payload_summary" not in serialized
    assert "payload" not in serialized


@pytest.mark.asyncio
async def test_prompt_preview_audit_endpoint_fails_closed_on_scenario_mismatch(auth_headers) -> None:
    from src.api import app

    body = _request_payload()
    body["runtime_injection"]["scenario"] = "s2"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/scenario/s1/prompt-preview/audit",
            headers=auth_headers,
            json=body,
        )

    assert response.status_code == 422
    assert "scenario mismatch" in response.text


def _request_payload() -> dict[str, object]:
    return {
        "contract": _quality_contract().model_dump(mode="json"),
        "compile_input": _compile_input(bundle=_bundle(["bat_hard_fixture"])).model_dump(mode="json"),
        "runtime_injection": _runtime_injection(["bat_hard_fixture"]).model_dump(mode="json"),
        "planned_injection": {"hard_token_ids": ["bat_hard_fixture"], "soft_token_ids": []},
    }


def _quality_contract() -> QualityContract:
    return QualityContract(
        contract_id="qc_s1_prompt_preview_fixture",
        scenario="s1",
        stage="prompt_preview",
        platform="tiktok",
        brand_id="momcozy",
    )


def _compile_input(
    *,
    capability: ProviderCapability | None = None,
    bundle: BrandConstraintBundle | None = None,
    shot: StoryboardShotSchema | None = None,
    compile_options: CompileOptions | None = None,
) -> PromptCompileInput:
    return PromptCompileInput(
        compile_id="pci_router_fixture",
        scenario="s1",
        step_name="video_prompts",
        shot=shot or _shot(),
        brand_bundle=bundle or _bundle([]),
        provider_capability=capability
        or ProviderCapability(
            capability_id="cap_seedance_fixture",
            provider="poyo",
            model="seedance-2",
            model_family="seedance",
            supports_reference_images=CapabilityValue.SUPPORTED,
            supports_negative_prompt=CapabilityValue.SUPPORTED,
            max_duration_seconds=15,
        ),
        platform_target=PlatformTarget(platform="tiktok", aspect_ratio="9:16"),
        compile_options=compile_options or CompileOptions(),
    )


def _shot() -> StoryboardShotSchema:
    return StoryboardShotSchema(
        shot_id="shot_001",
        scenario="s1",
        beat="product reveal",
        visual_description="Momcozy product reveal in warm soft light",
        motion_description="slow push-in",
        claim_evidence_refs=["claim_fixture"],
    )


def _bundle(token_ids: list[str]) -> BrandConstraintBundle:
    tokens = [_approved_token(token_id) for token_id in token_ids]
    return BrandConstraintBundle(
        bundle_id="bundle_prompt_preview_router_fixture",
        brand_id="momcozy",
        scenario="s1",
        step="video_prompts",
        hard_tokens=tokens,
        source_token_ids=[token.token_id for token in tokens],
    )


def _approved_token(token_id: str) -> BrandAssetToken:
    return BrandAssetToken(
        token_id=token_id,
        brand_id="momcozy",
        token_type="brand_voice",
        status=TokenStatus.APPROVED,
        strength=TokenStrength.HARD,
        payload={"raw": "must-not-leak"},
        payload_summary=["must-not-leak"],
        scenario_scope=["s1"],
        step_scope=["video_prompts"],
        rights_ref="rights_fixture",
        license_status=LicenseStatus.APPROVED,
        allowed_uses=[AllowedUse.GENERATION],
        review=TokenReview(review_status="approved", reviewed_by="self"),
    )


def _runtime_injection(hard_token_ids: list[str]) -> RuntimeInjectionResult:
    return RuntimeInjectionResult(
        scenario="s1",
        step="video_prompts",
        prompt_injection_allowed=True,
        brand_bundle_id="bundle_prompt_preview_router_fixture",
        hard_token_ids=hard_token_ids,
        source_token_ids=hard_token_ids,
    )
