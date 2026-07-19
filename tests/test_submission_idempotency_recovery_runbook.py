from __future__ import annotations

from pathlib import Path

RUNBOOK = Path("docs/runbooks/submission-idempotency-recovery.md")
ARTIFACT_RUNBOOK = Path("docs/runbooks/artifact-acceptance-lifecycle.md")

EXPECTED_TABLES = [
    "tenants",
    "admin_accounts",
    "api_keys",
    "admin_sessions",
    "threads",
    "pipeline_states",
    "brand_packages",
    "influencers",
    "video_metrics",
    "publish_logs",
    "error_logs",
    "audit_logs",
    "idempotency_records",
    "acceptance_records",
    "job_budget_accounts",
    "provider_cost_attempts",
]


def test_active_recovery_runbook_uses_the_current_16_table_contract() -> None:
    source = RUNBOOK.read_text(encoding="utf-8")

    assert "current 16-table" in source
    table_block = source.split("## 当前 active recovery schema contract", 1)[1].split(
        "## 前 2-5 分钟立即诊断", 1
    )[0]
    active_table_list = table_block.split("```text", 1)[1].split("```", 1)[0]
    assert "13 tables" not in active_table_list
    assert "13-table" not in active_table_list
    positions = [active_table_list.index(table) for table in EXPECTED_TABLES]
    assert positions == sorted(positions)
    assert "2026-07-10" in source and "12-table" in source


def test_active_recovery_runbook_orders_provider_off_backup_schema_readonly_binary() -> None:
    source = RUNBOOK.read_text(encoding="utf-8")
    section = source.split("## 生产迁移、部署与新恢复基线", 1)[1].split(
        "## 故障分类与响应", 1
    )[0]

    order = [
        "provider-off",
        "verified backup",
        "schema-first",
        "read-only",
        "provider-off binary rollout",
    ]
    positions = [section.index(marker) for marker in order]
    assert positions == sorted(positions)


def test_artifact_recovery_runbook_uses_current_set_and_provider_off_order() -> None:
    source = ARTIFACT_RUNBOOK.read_text(encoding="utf-8")

    assert "当前 application recovery set 精确为以下 16 个有序表" in source
    assert "verified backup → schema migration → application rollout" not in source
    assert "provider-off" in source
    assert "schema downgrade 不是 application rollback" in source
