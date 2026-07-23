"""Semantic contracts across exporter, alerts, dashboard, and promtool fixtures."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from src import telemetry_prometheus

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT = REPO_ROOT / "configs" / "prometheus-metrics-contract.yaml"
ALERTS = REPO_ROOT / "deploy" / "lighthouse" / "prometheus-alerts.yml"
DASHBOARD = REPO_ROOT / "deploy" / "lighthouse" / "grafana-dashboard.json"
RULE_TESTS = REPO_ROOT / "tests" / "fixtures" / "prometheus-alerts.test.yml"

QUERY_METRIC = re.compile(
    r"\b([a-zA-Z_:][a-zA-Z0-9_:]*(?:_total|_seconds(?:_bucket)?|_tasks))\b"
)
SELECTOR = re.compile(r"\b([a-zA-Z_:][a-zA-Z0-9_:]*)\{([^{}]*)\}")
MATCHER = re.compile(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*(=|!=|=~|!~)\s*"([^"]*)"')


def _contract() -> dict[str, Any]:
    payload = yaml.safe_load(CONTRACT.read_text())
    assert isinstance(payload, dict)
    return payload


def _queries() -> list[str]:
    alerts = yaml.safe_load(ALERTS.read_text())
    dashboard_raw = json.loads(DASHBOARD.read_text())
    dashboard = dashboard_raw.get("dashboard", dashboard_raw)
    return [
        *(str(rule["expr"]) for group in alerts["groups"] for rule in group["rules"]),
        *(
            str(target["expr"])
            for panel in dashboard["panels"]
            for target in panel.get("targets", [])
        ),
    ]


def test_contract_matches_registered_custom_collectors() -> None:
    expected = _contract()["metrics"]
    collectors = {name: getattr(telemetry_prometheus, name) for name in expected}

    assert set(collectors) == set(expected)
    for name, specification in expected.items():
        collector = collectors[name]
        assert getattr(collector, "_type") == specification["type"]
        assert list(getattr(collector, "_labelnames")) == specification["labels"]


def test_every_rule_and_dashboard_metric_exists_in_contract() -> None:
    contract_metrics = set(_contract()["metrics"])
    derived = {
        f"{name}_bucket": name
        for name, specification in _contract()["metrics"].items()
        if specification["type"] == "histogram"
    }
    for query in _queries():
        for metric in QUERY_METRIC.findall(query):
            base = derived.get(metric, metric)
            assert base in contract_metrics, f"query references unknown metric: {metric}"


def test_every_selector_label_and_exact_enum_matches_contract() -> None:
    metrics = _contract()["metrics"]
    derived = {
        f"{name}_bucket": name
        for name, specification in metrics.items()
        if specification["type"] == "histogram"
    }
    for query in _queries():
        for metric, selector in SELECTOR.findall(query):
            base = derived.get(metric, metric)
            assert base in metrics, f"selector references unknown metric: {metric}"
            specification = metrics[base]
            matchers = MATCHER.findall(selector)
            assert matchers, f"selector has no parseable matcher: {metric}{{{selector}}}"
            for label, operator, value in matchers:
                assert label in specification["labels"], (
                    f"{metric} selector references unknown label: {label}"
                )
                allowed = specification.get("enums", {}).get(label)
                if allowed is not None and operator in {"=", "!="}:
                    assert value in allowed, (
                        f"{metric} selector references unknown {label} enum: {value}"
                    )


def test_queries_use_canonical_labels_and_enums() -> None:
    serialized = "\n".join(_queries())
    for forbidden in ('status="error"', "step_name", "endpoint", 'status=~"5.."'):
        assert forbidden not in serialized
    assert 'status="failure"' in serialized
    assert 'status_class="5xx"' in serialized
    assert "by (le, step)" in serialized
    assert "by (le, route)" in serialized


def test_dashboard_contains_no_stale_legend_label_aliases() -> None:
    dashboard = DASHBOARD.read_text()
    assert "step_name" not in dashboard
    assert "endpoint" not in dashboard


def test_rule_fixture_covers_every_alert_name_and_phase() -> None:
    alerts = yaml.safe_load(ALERTS.read_text())
    expected = {
        rule["alert"]
        for group in alerts["groups"]
        for rule in group["rules"]
        if "alert" in rule
    }
    fixture = yaml.safe_load(RULE_TESTS.read_text())
    phases: dict[str, set[str]] = {}
    for group in fixture["tests"]:
        alert_name, phase = group["name"].split(" / ", 1)
        phases.setdefault(alert_name, set()).add(phase)

    assert set(phases) == expected
    assert all(value == {"non-firing", "firing", "resolved"} for value in phases.values())
