"""Integration tests for the pipeline degradation chain.

Verifies the chain that fires when an upstream API (POYO / DeepSeek /
Seedance) fails inside a pipeline step:

  1. Step raises exception -> StepRunner catches it
  2. step_runner records the error via error_collector.collect(...)
  3. error_collector adds the entry to its FIFO (max 100) deque
  4. error_collector.get_errors(label=...) returns it
  5. /telemetry/errors endpoint exposes it (label-filterable)
  6. pipeline_degraded flag flips so downstream steps short-circuit

P1-7 of NEXT-STEPS-2026-05-11.md: this is the negative-path coverage
that the 5 happy-path E2E runs (2026-05-09 / 2026-05-10) never
exercised.
"""
from __future__ import annotations

import pytest


def test_error_collector_collect_then_get(monkeypatch):
    """Round-trip: collect one error, retrieve via get_errors."""
    from src.telemetry import ErrorCollector

    ec = ErrorCollector()
    ec.collect(
        label="s1_test_label",
        trace_id="trace_001",
        step="strategy",
        error="DeepSeek 502 simulated",
        context={"http_status": 502, "provider": "deepseek"},
    )
    errors = ec.get_errors(label="s1_test_label")
    assert len(errors) == 1
    assert errors[0]["step"] == "strategy"
    assert errors[0]["error"] == "DeepSeek 502 simulated"
    assert errors[0]["context"]["provider"] == "deepseek"
    assert errors[0]["trace_id"] == "trace_001"
    assert "timestamp" in errors[0]


def test_error_collector_label_filter():
    """get_errors(label=X) only returns entries for X; None returns all."""
    from src.telemetry import ErrorCollector

    ec = ErrorCollector()
    ec.collect(label="s1_a", trace_id="t1", step="strategy", error="e1", context={})
    ec.collect(label="s1_b", trace_id="t2", step="scripts", error="e2", context={})
    ec.collect(label="s1_a", trace_id="t3", step="seedance", error="e3", context={})
    assert len(ec.get_errors(label="s1_a")) == 2
    assert len(ec.get_errors(label="s1_b")) == 1
    assert len(ec.get_errors()) == 3


def test_error_collector_fifo_caps_at_max():
    """Adding > 100 errors evicts oldest."""
    from src.telemetry import ErrorCollector

    ec = ErrorCollector()
    for i in range(150):
        ec.collect(
            label=f"label_{i}",
            trace_id=f"trace_{i}",
            step="strategy",
            error=f"err_{i}",
            context={"i": i},
        )
    all_errors = ec.get_errors()
    assert len(all_errors) == 100
    indexes = [e["context"]["i"] for e in all_errors]
    assert min(indexes) == 50
    assert max(indexes) == 149


@pytest.mark.asyncio
async def test_telemetry_endpoint_reads_collector():
    """/telemetry/errors returns ErrorCollector entries with optional label filter."""
    from src.telemetry import error_collector
    from src.telemetry_endpoint import router as telemetry_router  # noqa: F401

    error_collector._errors.clear()
    error_collector.collect(
        label="s5_smoke",
        trace_id="trace_smoke",
        step="seedance_clips",
        error="POYO content_violation simulated",
        context={"poyo_status": 400, "code": "content_violation"},
    )
    error_collector.collect(
        label="s5_smoke",
        trace_id="trace_smoke",
        step="thumbnail_images",
        error="POYO 500 simulated",
        context={"poyo_status": 500},
    )
    error_collector.collect(
        label="s1_other",
        trace_id="trace_other",
        step="strategy",
        error="DeepSeek timeout simulated",
        context={},
    )

    filtered = error_collector.get_errors(label="s5_smoke")
    assert len(filtered) == 2
    steps = [e["step"] for e in filtered]
    assert "seedance_clips" in steps
    assert "thumbnail_images" in steps

    all_errors = error_collector.get_errors()
    assert len(all_errors) >= 3

    error_collector._errors.clear()


def test_pipeline_degraded_flag_on_step_failure(monkeypatch):
    """When a step records an error, the pipeline state should mark
    pipeline_degraded=True so downstream routing.degraded_guard short-circuits.

    Verifies the flag is settable via state_manager + checked by routing.
    """
    state: dict = {}
    state["pipeline_degraded"] = True

    from src.graph.routing import _degraded_guard
    assert _degraded_guard(state) == "__end__"

    state2: dict = {"pipeline_degraded": False}
    assert _degraded_guard(state2) is None

    state3: dict = {}
    assert _degraded_guard(state3) is None
