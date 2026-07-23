from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
MONITORING = REPO_ROOT / "deploy" / "lighthouse" / "monitoring"
OVERLAY = REPO_ROOT / "deploy" / "lighthouse" / "docker-compose.monitoring.yml"
NGINX = REPO_ROOT / "deploy" / "lighthouse" / "ai_video_locations.conf"
MAKEFILE = REPO_ROOT / "Makefile"
CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"
ACTIVE_MONITORING_RUNBOOKS = (
    REPO_ROOT / "docs" / "runbooks" / "deepseek-timeout.md",
    REPO_ROOT / "docs" / "runbooks" / "db-pool-exhausted.md",
)


def _yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text())
    assert isinstance(payload, dict)
    return payload


def test_prometheus_owns_exact_internal_scrape_and_rule_files() -> None:
    config = _yaml(MONITORING / "prometheus.yml")
    assert config["rule_files"] == ["/etc/prometheus/prometheus-alerts.yml"]
    job = config["scrape_configs"][0]
    assert job["metrics_path"] == "/metrics"
    assert job["static_configs"] == [{"targets": ["backend:8001"]}]
    assert config["alerting"]["alertmanagers"][0]["static_configs"] == [
        {"targets": ["alertmanager:9093"]}
    ]


def test_alertmanager_fixture_receiver_sends_resolved_only_internally() -> None:
    config = _yaml(MONITORING / "alertmanager.yml")
    webhook = config["receivers"][0]["webhook_configs"][0]
    assert webhook == {
        "url": "http://alert-receiver:8080/alerts",
        "send_resolved": True,
    }


def test_monitoring_overlay_is_digest_pinned_internal_and_unpublished() -> None:
    overlay = _yaml(OVERLAY)
    assert overlay["networks"]["monitoring_internal"]["internal"] is True
    for name in ("prometheus", "alertmanager", "grafana"):
        service = overlay["services"][name]
        assert "@sha256:" in service["image"]
        assert service["networks"] == ["monitoring_internal"]
        assert "ports" not in service
    receiver = overlay["services"]["alert-receiver"]
    assert receiver["networks"] == ["monitoring_internal"]
    assert receiver["command"] == [
        "/app/.venv/bin/python",
        "/app/scripts/monitoring_fixture_receiver.py",
    ]
    assert "ports" not in receiver
    assert "secrets" not in receiver
    assert overlay["secrets"]["grafana_admin_password"] == {
        "file": "${GRAFANA_ADMIN_PASSWORD_FILE:?GRAFANA_ADMIN_PASSWORD_FILE is required}"
    }


def test_public_nginx_does_not_proxy_metrics() -> None:
    nginx = NGINX.read_text()
    block = nginx.split("location = /metrics {", 1)[1].split("}", 1)[0]
    assert "return 404;" in block
    assert "proxy_pass" not in block


def test_promtool_digest_gate_is_in_make_and_ci() -> None:
    makefile = MAKEFILE.read_text()
    assert "prom/prometheus:v3.13.1@sha256:" in makefile
    assert "prom/alertmanager:v0.32.1@sha256:" in makefile
    assert "promtool" in makefile
    assert "amtool" in makefile
    assert "check config /etc/prometheus/prometheus.yml" in makefile
    assert "docker-compose.monitoring.yml --profile monitoring config --quiet" in makefile
    assert "check rules" in makefile
    assert "test rules" in makefile
    assert "make monitoring-check" in CI.read_text()


def test_docker_validation_prepares_locked_python_before_monitoring_tests() -> None:
    workflow = _yaml(CI)
    steps = workflow["jobs"]["docker-build"]["steps"]
    monitoring_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("run") == "make monitoring-check"
    )
    setup_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("uses") == "actions/setup-python@v6"
    )
    install_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("run") == "python -m pip install uv==0.11.11"
    )
    sync_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("run") == "uv sync --locked --extra dev"
    )

    assert steps[setup_index]["with"]["python-version"] == "3.12.13"
    assert setup_index < install_index < sync_index < monitoring_index


def test_active_runbooks_do_not_restore_removed_fake_metric_families() -> None:
    runbooks = "\n".join(path.read_text() for path in ACTIVE_MONITORING_RUNBOOKS)
    for unsupported in (
        "llm_api_errors_total",
        "llm_api_duration_seconds",
        "db_pool_available_connections",
        "db_pool_total_connections",
        "db_pool_acquire_duration_seconds",
    ):
        assert unsupported not in runbooks
    assert "printenv DEEPSEEK_API_KEY" not in runbooks
