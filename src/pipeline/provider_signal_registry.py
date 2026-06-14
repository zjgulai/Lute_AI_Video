"""Provider market-signal helpers for no-token capability planning."""

from __future__ import annotations

from src.models.commercial_contracts import (
    CapabilitySnapshot,
    ExperimentBacklogItem,
    ProviderCapability,
    ProviderSignalLedger,
    TechniquePattern,
    evidence_allows_production_default,
)


def build_capability_snapshot_from_signal(
    *,
    snapshot_id: str,
    signal: ProviderSignalLedger,
    capability: ProviderCapability,
) -> CapabilitySnapshot:
    """Create a capability snapshot from one evidence-graded signal."""
    warnings: list[str] = []
    if not evidence_allows_production_default(signal.evidence_level):
        warnings.append("signal evidence is not strong enough for production default")

    return CapabilitySnapshot(
        snapshot_id=snapshot_id,
        provider=signal.provider,
        model=signal.model,
        capability=capability,
        evidence_level=signal.evidence_level,
        source_signal_ids=[signal.signal_id],
        captured_at=signal.observed_at,
        production_default_eligible=False,
        warnings=warnings,
    )


def build_experiment_backlog_item(
    *,
    experiment_id: str,
    signal: ProviderSignalLedger,
    hypothesis: str,
    target_scenarios: list[str],
) -> ExperimentBacklogItem:
    """Turn a market signal into a fixture-first experiment backlog item."""
    return ExperimentBacklogItem(
        experiment_id=experiment_id,
        provider=signal.provider,
        model=signal.model,
        hypothesis=hypothesis,
        source_signal_ids=[signal.signal_id],
        evidence_level=signal.evidence_level,
        target_scenarios=target_scenarios,
        allowed_actions=["fixture"],
        production_default_candidate=False,
    )


def build_technique_pattern_from_signal(
    *,
    pattern_id: str,
    signal: ProviderSignalLedger,
    name: str,
    applicable_scenarios: list[str],
    description: str,
) -> TechniquePattern:
    return TechniquePattern(
        pattern_id=pattern_id,
        name=name,
        source_signal_ids=[signal.signal_id],
        applicable_scenarios=applicable_scenarios,
        evidence_level=signal.evidence_level,
        description=description,
        implementation_status="candidate",
    )
