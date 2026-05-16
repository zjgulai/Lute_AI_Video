"""Tests for new Prometheus metrics added in MASTER-PLAN TODO-C3-C7.

Existing 6 metrics (pipeline_runs / pipeline_duration / pipeline_errors /
step_duration / step_failures / active_pipelines) are not in scope here \u2014
they were added earlier and tested elsewhere. This file only pins the
5 new metrics so they don't regress on a refactor.
"""
from __future__ import annotations

import pytest

prom = pytest.importorskip("prometheus_client")  # noqa: F841

from src.telemetry_prometheus import (
    admin_login_attempts_total,
    db_pool_available_connections,
    db_pool_size,
    llm_api_duration_seconds,
    llm_api_errors_total,
    prometheus_content,
    record_admin_login,
    record_llm_call,
    tenant_active_count,
    update_db_pool_stats,
    update_tenant_active_count,
)


def _scrape() -> str:
    body, _ = prometheus_content()
    return body.decode()


class TestLlmApiMetrics:
    def test_record_llm_success_increments_duration_only(self):
        record_llm_call(provider="deepseek", duration_sec=2.5, success=True)
        text = _scrape()
        assert "llm_api_duration_seconds_count" in text
        assert 'provider="deepseek"' in text

    def test_record_llm_failure_increments_errors(self):
        record_llm_call(provider="poyo", duration_sec=10.0, success=False, error_kind="timeout")
        text = _scrape()
        assert 'llm_api_errors_total{error_kind="timeout",provider="poyo"}' in text

    def test_unknown_error_kind_defaults_to_unknown(self):
        record_llm_call(provider="siliconflow", duration_sec=1.0, success=False)
        text = _scrape()
        assert 'error_kind="unknown"' in text


class TestAdminLoginMetric:
    def test_outcome_label_recorded(self):
        record_admin_login("success")
        record_admin_login("invalid_creds")
        record_admin_login("rate_limited")
        text = _scrape()
        for outcome in ("success", "invalid_creds", "rate_limited"):
            assert f'admin_login_attempts_total{{outcome="{outcome}"}}' in text


class TestDbPoolGauges:
    def test_update_db_pool_stats_sets_both_gauges(self):
        update_db_pool_stats(available=3, size=10)
        text = _scrape()
        assert "db_pool_available_connections 3.0" in text
        assert "db_pool_size 10.0" in text

    def test_update_to_zero_indicates_saturation(self):
        update_db_pool_stats(available=0, size=10)
        text = _scrape()
        assert "db_pool_available_connections 0.0" in text


class TestTenantActiveGauge:
    def test_update_tenant_count(self):
        update_tenant_active_count(42)
        text = _scrape()
        assert "tenant_active_count 42.0" in text

    def test_zero_tenants_recorded(self):
        update_tenant_active_count(0)
        text = _scrape()
        assert "tenant_active_count 0.0" in text


class TestMetricsExist:
    """Metric registration smoke-tests \u2014 ensures the public exporter names
    don't disappear from refactors."""

    @pytest.mark.parametrize(
        "metric",
        [
            llm_api_errors_total,
            llm_api_duration_seconds,
            db_pool_available_connections,
            db_pool_size,
            admin_login_attempts_total,
            tenant_active_count,
        ],
    )
    def test_metric_is_collector(self, metric):
        assert hasattr(metric, "_name")
