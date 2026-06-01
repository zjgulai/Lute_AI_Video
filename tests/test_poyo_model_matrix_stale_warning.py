"""Static guard for the poyo model matrix stale-snapshot warning."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = REPO_ROOT / "docs" / "architecture" / "poyo-model-matrix-stable.md"
CONTRACT_PATH = REPO_ROOT / "configs" / "poyo-model-matrix-stale-warning-contract.json"
RUNBOOK_PATH = REPO_ROOT / "docs" / "runbooks" / "poyo-model-matrix-stale-warning.md"
DOCS_SCOPE_PATH = REPO_ROOT / "configs" / "docs-link-check-scope.txt"
CI_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _contract() -> dict[str, Any]:
    assert CONTRACT_PATH.exists(), "poyo model matrix stale-warning contract is missing"
    data = json.loads(CONTRACT_PATH.read_text())
    assert isinstance(data, dict), "poyo model matrix contract must be a JSON object"
    return data


def _scope_targets() -> set[str]:
    return {
        line.strip()
        for line in DOCS_SCOPE_PATH.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    }


def test_poyo_model_matrix_declares_snapshot_boundary_and_not_latest() -> None:
    text = MATRIX_PATH.read_text()

    assert "快照边界（2026-05-31）" in text
    assert "2026-05 的 poyo.ai 模型目录" in text
    assert "不保证代表 poyo.ai 当前最新目录、价格或审核规则" in text
    assert "任何真实 token 消耗" in text
    assert "部署默认模型切换" in text
    assert "成本测算前" in text
    assert "重新核对 poyo.ai 当前产品页面/API 文档" in text
    assert "同步 `src/pipeline/model_thresholds.py` 与本表" in text
    assert "2026-05 snapshot" in text


def test_poyo_model_matrix_stale_warning_contract_is_machine_readable() -> None:
    contract = _contract()
    matrix_text = MATRIX_PATH.read_text()

    assert contract["status"] == "stable"
    assert contract["matrix_path"] == "docs/architecture/poyo-model-matrix-stable.md"
    assert contract["code_counterpart"] == "src/pipeline/model_thresholds.py"
    assert contract["runbook"] == "docs/runbooks/poyo-model-matrix-stale-warning.md"
    assert contract["snapshot_date"] == "2026-05-31"
    assert contract["snapshot_catalog"] == "2026-05"
    assert contract["must_not_claim_latest"] is True
    assert contract["pre_recharge_revalidation_required"] is True
    assert contract["no_token_boundary"] is True

    for phrase in contract["required_matrix_phrases"]:
        assert phrase in matrix_text


def test_poyo_model_matrix_runbook_documents_revalidation_workflow() -> None:
    contract = _contract()
    runbook_text = RUNBOOK_PATH.read_text()

    assert "poyo-model-matrix-stale-warning-contract.json" in runbook_text
    assert contract["matrix_path"] in runbook_text
    assert contract["code_counterpart"] in runbook_text
    assert "tests/test_poyo_model_matrix_stale_warning.py" in runbook_text
    assert "poyo.ai 当前产品页面/API 文档" in runbook_text
    assert "充值" in runbook_text
    assert "RUN_TOKEN_SMOKE=1" in runbook_text
    assert "不执行" in runbook_text


def test_poyo_model_matrix_warning_docs_are_link_checked() -> None:
    scope_targets = _scope_targets()
    ci_text = CI_PATH.read_text()

    assert "docs/architecture/poyo-model-matrix-stable.md" in scope_targets
    assert "docs/runbooks/poyo-model-matrix-stale-warning.md" in scope_targets
    assert "docs/runbooks/poyo-model-matrix-stale-warning.md" in ci_text
