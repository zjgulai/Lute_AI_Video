"""Regression tests for typed runtime boundary contracts."""

from __future__ import annotations

import inspect
from typing import get_type_hints

from src.models.runtime_contracts import (
    ContinuityAuditSummary,
    FastModeResult,
    SeedanceVideoResult,
    TelemetryErrorsResponse,
    TelemetrySummary,
)


def test_fast_mode_generate_return_contract_is_typed():
    from src.services.fast_mode import FastModeService

    hints = get_type_hints(FastModeService.generate)
    assert hints["return"] is FastModeResult


def test_seedance_public_generation_methods_return_typed_contract():
    from src.tools.seedance_client import SeedanceClient

    assert get_type_hints(SeedanceClient.text_to_video)["return"] is SeedanceVideoResult
    assert get_type_hints(SeedanceClient.image_to_video)["return"] is SeedanceVideoResult
    assert get_type_hints(SeedanceClient._stub_result)["return"] is SeedanceVideoResult


def test_seedance_stub_shape_matches_contract():
    from src.tools.seedance_client import SeedanceClient

    result = SeedanceClient(api_key="")._stub_result(prompt="safe prompt", mode="unit_test")

    assert result["video_url"].startswith("[SEEDANCE_STUB")
    assert result["local_path"].endswith(".mp4")
    assert result["prompt_used"] == "safe prompt"
    assert result["duration"] == 0
    assert result["_stub_mode"] == "unit_test"
    assert result["simulated"] is True


def test_telemetry_endpoint_return_contracts_are_typed():
    import src.telemetry_endpoint as telemetry_endpoint

    route_returns = {
        route.path: get_type_hints(route.endpoint).get("return")
        for route in telemetry_endpoint.router.routes
        if hasattr(route, "endpoint")
    }

    assert route_returns["/telemetry/metrics"] is TelemetrySummary
    assert route_returns["/telemetry/errors"] is TelemetryErrorsResponse


def test_continuity_audit_summary_return_contract_is_typed():
    from src.pipeline.continuity_utils import build_continuity_audit_summary

    hints = get_type_hints(build_continuity_audit_summary)
    assert hints["return"] is ContinuityAuditSummary


def test_fast_mode_no_longer_uses_union_attr_ignores():
    from src.services.fast_mode import FastModeService

    source = inspect.getsource(FastModeService.generate)
    assert "type: ignore[union-attr]" not in source
