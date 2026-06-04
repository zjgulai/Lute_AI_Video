from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.models.commercial_contracts import (
    CapabilityValue,
    EvidenceLevel,
    ProviderCapability,
    ProviderSignalLedger,
    evidence_allows_production_default,
)
from src.pipeline.provider_signal_registry import (
    build_capability_snapshot_from_signal,
    build_experiment_backlog_item,
    build_technique_pattern_from_signal,
)

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "commercial_video"


def test_aihot_signal_defaults_to_market_signal_not_production_default():
    signal = _fixture_signal("sig_aihot_seedance_20260604")

    assert signal.evidence_level == EvidenceLevel.AIHOT_SIGNAL
    assert signal.production_default_eligible is False
    assert evidence_allows_production_default(signal.evidence_level) is False


def test_aihot_signal_cannot_claim_production_default():
    data = _fixture_signal_data("sig_aihot_seedance_20260604")
    data["production_default_eligible"] = True

    with pytest.raises(ValidationError, match="too weak for production default"):
        ProviderSignalLedger.model_validate(data)


def test_capability_snapshot_from_aihot_signal_gets_warning_and_stays_not_default():
    signal = _fixture_signal("sig_aihot_seedance_20260604")
    capability = ProviderCapability(
        capability_id="cap_seedance_fixture",
        provider="poyo",
        model="seedance-2",
        model_family="seedance",
        supports_reference_images=CapabilityValue.UNKNOWN,
    )

    snapshot = build_capability_snapshot_from_signal(
        snapshot_id="snap_seedance_fixture",
        signal=signal,
        capability=capability,
    )

    assert snapshot.production_default_eligible is False
    assert snapshot.source_signal_ids == [signal.signal_id]
    assert snapshot.warnings == ["signal evidence is not strong enough for production default"]
    assert snapshot.capability.feature_is_supported("supports_reference_images") is False


def test_official_doc_evidence_is_eligible_but_not_auto_enabled():
    signal = _fixture_signal("sig_official_runway_20260604")

    assert evidence_allows_production_default(signal.evidence_level) is True

    snapshot = build_capability_snapshot_from_signal(
        snapshot_id="snap_runway_fixture",
        signal=signal,
        capability=ProviderCapability(
            capability_id="cap_runway_fixture",
            provider="runway",
            model="gen-3",
            model_family="runway",
        ),
    )

    assert snapshot.production_default_eligible is False
    assert snapshot.warnings == []


def test_market_signal_only_creates_fixture_first_experiment_backlog():
    signal = _fixture_signal("sig_aihot_seedance_20260604")

    item = build_experiment_backlog_item(
        experiment_id="exp_seedance_fixture",
        signal=signal,
        hypothesis="Seedance profile may improve short product clips",
        target_scenarios=["s1", "s5"],
    )

    assert item.allowed_actions == ["fixture"]
    assert item.production_default_candidate is False
    assert item.evidence_level == EvidenceLevel.AIHOT_SIGNAL


def test_technique_pattern_from_signal_remains_candidate():
    signal = _fixture_signal("sig_aihot_seedance_20260604")

    pattern = build_technique_pattern_from_signal(
        pattern_id="pattern_storyboard_first_fixture",
        signal=signal,
        name="storyboard-first i2v",
        applicable_scenarios=["s1", "s2"],
        description="Image storyboard before short video generation",
    )

    assert pattern.implementation_status == "candidate"
    assert pattern.evidence_level == EvidenceLevel.AIHOT_SIGNAL


def _fixture_signal(signal_id: str) -> ProviderSignalLedger:
    return ProviderSignalLedger.model_validate(_fixture_signal_data(signal_id))


def _fixture_signal_data(signal_id: str) -> dict[str, object]:
    data = json.loads((FIXTURE_ROOT / "provider_market_signals.json").read_text())
    for signal in data["signals"]:
        if signal["signal_id"] == signal_id:
            return signal
    raise AssertionError(f"missing fixture signal {signal_id}")
