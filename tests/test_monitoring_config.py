"""Static validation of monitoring config (NEXT-3 code-side).

Verifies that deploy/lighthouse/prometheus-alerts.yml and
deploy/lighthouse/grafana-dashboard.json are syntactically valid AND
structurally conform to the Prometheus rule schema / Grafana dashboard
schema. Catches regressions before they hit production reload.

Does NOT exercise the running Prometheus / Grafana instance (that would
require SSH access). Catches config-level breakage that an actionlint /
prom-tool check would catch.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
ALERTS_PATH = REPO_ROOT / "deploy" / "lighthouse" / "prometheus-alerts.yml"
DASHBOARD_PATH = REPO_ROOT / "deploy" / "lighthouse" / "grafana-dashboard.json"


class TestPrometheusAlerts:

    @pytest.fixture
    def alerts(self):
        with open(ALERTS_PATH) as f:
            return yaml.safe_load(f)

    def test_file_exists(self):
        assert ALERTS_PATH.exists(), f"Missing {ALERTS_PATH}"

    def test_top_level_groups_key(self, alerts):
        assert "groups" in alerts
        assert isinstance(alerts["groups"], list)
        assert len(alerts["groups"]) >= 1

    def test_each_group_has_required_fields(self, alerts):
        for group in alerts["groups"]:
            assert "name" in group, f"group missing name: {group}"
            assert "rules" in group, f"group missing rules: {group['name']}"
            assert isinstance(group["rules"], list)

    def test_each_rule_has_required_fields(self, alerts):
        for group in alerts["groups"]:
            for rule in group["rules"]:
                assert "alert" in rule or "record" in rule, (
                    f"rule missing alert/record: {rule}"
                )
                assert "expr" in rule, f"rule missing expr: {rule.get('alert', rule.get('record'))}"

    def test_alert_rules_have_severity_label(self, alerts):
        for group in alerts["groups"]:
            for rule in group["rules"]:
                if "alert" not in rule:
                    continue
                labels = rule.get("labels") or {}
                assert "severity" in labels, (
                    f"alert {rule['alert']} missing severity label"
                )
                assert labels["severity"] in ("warning", "critical"), (
                    f"alert {rule['alert']} has invalid severity: {labels['severity']}"
                )

    def test_alert_rules_have_annotations(self, alerts):
        for group in alerts["groups"]:
            for rule in group["rules"]:
                if "alert" not in rule:
                    continue
                annotations = rule.get("annotations") or {}
                assert "summary" in annotations, (
                    f"alert {rule['alert']} missing summary annotation"
                )

    def test_at_least_four_alerts_defined(self, alerts):
        alert_count = sum(
            1
            for group in alerts["groups"]
            for rule in group["rules"]
            if "alert" in rule
        )
        assert alert_count >= 4, f"Expected ≥4 alerts (C9 scope), got {alert_count}"

    def test_promql_expr_is_non_empty_string(self, alerts):
        for group in alerts["groups"]:
            for rule in group["rules"]:
                expr = rule.get("expr", "")
                assert isinstance(expr, str) and expr.strip(), (
                    f"rule {rule.get('alert', rule.get('record'))} has empty expr"
                )


class TestGrafanaDashboard:

    @pytest.fixture
    def dashboard_raw(self):
        with open(DASHBOARD_PATH) as f:
            return json.load(f)

    @pytest.fixture
    def dashboard(self, dashboard_raw):
        return dashboard_raw.get("dashboard", dashboard_raw)

    def test_file_exists(self):
        assert DASHBOARD_PATH.exists(), f"Missing {DASHBOARD_PATH}"

    def test_has_title(self, dashboard):
        assert "title" in dashboard
        assert dashboard["title"].strip()

    def test_has_schema_version(self, dashboard):
        assert "schemaVersion" in dashboard
        assert isinstance(dashboard["schemaVersion"], int)
        assert dashboard["schemaVersion"] >= 30

    def test_has_panels(self, dashboard):
        assert "panels" in dashboard
        assert isinstance(dashboard["panels"], list)
        assert len(dashboard["panels"]) >= 1

    def test_each_panel_has_required_fields(self, dashboard):
        for panel in dashboard["panels"]:
            assert "id" in panel, f"panel missing id: {panel.get('title')}"
            assert "title" in panel, f"panel id={panel.get('id')} missing title"
            assert "type" in panel, f"panel '{panel.get('title')}' missing type"

    def test_each_panel_has_at_least_one_target(self, dashboard):
        for panel in dashboard["panels"]:
            if panel.get("type") in ("row", "text"):
                continue
            targets = panel.get("targets") or []
            assert len(targets) >= 1, (
                f"panel '{panel.get('title')}' has no PromQL targets"
            )

    def test_promql_targets_non_empty(self, dashboard):
        for panel in dashboard["panels"]:
            for target in panel.get("targets", []):
                expr = target.get("expr", "")
                assert isinstance(expr, str) and expr.strip(), (
                    f"panel '{panel.get('title')}' target has empty expr"
                )
