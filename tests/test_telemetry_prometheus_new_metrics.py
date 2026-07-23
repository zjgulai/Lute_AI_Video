"""Canonical Prometheus metric call-site contracts."""

from __future__ import annotations

from pathlib import Path

import pytest
from prometheus_client import REGISTRY

from src.telemetry_prometheus import (
    active_background_tasks,
    api_request_duration_seconds,
    api_requests_total,
    prometheus_content,
    record_http_request,
    update_active_background_tasks,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _sample(name: str, labels: dict[str, str] | None = None) -> float:
    return REGISTRY.get_sample_value(name, labels or {}) or 0.0


def _scrape() -> str:
    body, _ = prometheus_content()
    return body.decode()


def test_http_metric_uses_route_template_and_status_class() -> None:
    labels = {"method": "GET", "route": "/media/{path:path}", "status_class": "4xx"}
    before = _sample("api_requests_total", labels)

    record_http_request("get", "/media/{path:path}", 404, 0.125)

    assert _sample("api_requests_total", labels) == before + 1
    assert _sample(
        "api_request_duration_seconds_count",
        {"method": "GET", "route": "/media/{path:path}"},
    ) >= 1


def test_http_metric_collapses_unknown_methods_to_bounded_enum() -> None:
    labels = {
        "method": "OTHER",
        "route": "__unmatched__",
        "status_class": "4xx",
    }
    before = _sample("api_requests_total", labels)

    record_http_request("BREW-UNBOUNDED", "__unmatched__", 418, 0.001)

    assert _sample("api_requests_total", labels) == before + 1
    assert 'method="BREW-UNBOUNDED"' not in _scrape()


def test_background_task_gauge_rejects_negative_counts() -> None:
    update_active_background_tasks(3)
    assert _sample("active_background_tasks") == 3
    with pytest.raises(ValueError, match="cannot be negative"):
        update_active_background_tasks(-1)


@pytest.mark.parametrize(
    "metric",
    [api_requests_total, api_request_duration_seconds, active_background_tasks],
)
def test_metric_is_registered(metric: object) -> None:
    assert hasattr(metric, "_name")


def test_unwired_zero_value_metric_families_are_not_exported() -> None:
    text = _scrape()
    for unsupported in (
        "active_pipelines",
        "llm_api_errors_total",
        "llm_api_duration_seconds",
        "db_pool_available_connections",
        "db_pool_size",
        "admin_login_attempts_total",
        "tenant_active_count",
    ):
        assert unsupported not in text


def test_s5_wrapper_does_not_emit_a_second_pipeline_completion() -> None:
    source = (REPO_ROOT / "src" / "pipeline" / "s5_brand_vlog_pipeline.py").read_text()
    assert "pipeline_metrics.record_pipeline" not in source
