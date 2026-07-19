"""Guard OpenAPI generated TypeScript types against backend schema drift."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_openapi_types_drift.py"
PACKAGE_JSON = REPO_ROOT / "web" / "package.json"
CONTRACT = REPO_ROOT / "configs" / "openapi-generated-types-drift-contract.yaml"
RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "openapi-generated-types-drift.md"
GENERATED_TYPES = REPO_ROOT / "web" / "src" / "types" / "api.generated.ts"


def test_openapi_typegen_scripts_use_local_schema_and_pinned_generator():
    package = json.loads(PACKAGE_JSON.read_text())
    scripts = package["scripts"]

    assert scripts["typegen:api"] == "../.venv/bin/python ../scripts/check_openapi_types_drift.py --write"
    assert scripts["check:api-types"] == "../.venv/bin/python ../scripts/check_openapi_types_drift.py"
    assert "http://" not in scripts["typegen:api"]
    assert "https://" not in scripts["typegen:api"]
    assert package["devDependencies"]["openapi-typescript"] == "7.13.0"


def test_openapi_drift_guard_detects_stale_types_without_mutating(tmp_path):
    generated_types = tmp_path / "api.generated.ts"
    schema_path = tmp_path / "openapi.json"
    unexpected_repo_output = REPO_ROOT / "None"
    generated_types.write_text("// stale generated types\n", encoding="utf-8")

    assert not unexpected_repo_output.exists()

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--generated-types",
            str(generated_types),
            "--schema-path",
            str(schema_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "api.generated.ts is stale" in result.stderr
    assert generated_types.read_text(encoding="utf-8") == "// stale generated types\n"
    assert schema_path.exists()
    assert not unexpected_repo_output.exists()


def test_openapi_drift_guard_write_mode_updates_target_from_local_schema(tmp_path):
    generated_types = tmp_path / "api.generated.ts"
    schema_path = tmp_path / "openapi.json"
    generated_types.write_text("// stale generated types\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--write",
            "--generated-types",
            str(generated_types),
            "--schema-path",
            str(schema_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    generated = generated_types.read_text(encoding="utf-8")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    assert result.returncode == 0
    assert "export interface paths" in generated
    assert '"/health"' in generated
    assert "/health" in schema["paths"]


def test_openapi_drift_contract_and_runbook_document_no_remote_schema():
    assert CONTRACT.exists()
    assert RUNBOOK.exists()
    contract = CONTRACT.read_text(encoding="utf-8")
    runbook = RUNBOOK.read_text(encoding="utf-8")

    for token in [
        "scripts/check_openapi_types_drift.py",
        "web/src/types/api.generated.ts",
        "openapi-typescript",
        "no_remote_schema: true",
    ]:
        assert token in contract

    for token in [
        ".venv/bin/python scripts/check_openapi_types_drift.py",
        "npm run check:api-types",
        "npm run typegen:api",
        "不访问生产",
    ]:
        assert token in runbook


def test_generated_types_include_acceptance_create_read_revoke_only():
    generated = GENERATED_TYPES.read_text(encoding="utf-8")

    for token in [
        '"/acceptance-records"',
        '"/acceptance-records/{acceptance_id}"',
        '"/acceptance-records/{acceptance_id}/revoke"',
        "AcceptanceRecordResponse",
    ]:
        assert token in generated
    assert '"/acceptance-records/{acceptance_id}/consume"' not in generated

    create_operation = re.search(
        r"(?ms)^    create_acceptance_record_acceptance_records_post: \{\n"
        r".*?^    \};$",
        generated,
    )
    assert create_operation is not None
    create_contract = create_operation.group(0)
    assert "requestBody: {" in create_contract
    assert "requestBody?: never;" not in create_contract
    for field in [
        "source_resource_type",
        "source_resource_id",
        "artifact_path",
        "decision",
        "review_notes",
        "expires_in_seconds?",
    ]:
        assert field in create_contract
    assert 'source_resource_type: "fast" | "scenario";' in create_contract
    assert 'decision: "accepted" | "rejected";' in create_contract


def test_generated_types_include_w1_25_receipt_and_attempt_readback() -> None:
    generated = GENERATED_TYPES.read_text(encoding="utf-8")

    for token in [
        '"/distribution/publish-attempts/{attempt_id}"',
        "PublishAttemptReadbackResponse",
        "PublishReceiptV1",
        "DurableTikTokStatusResponse",
        "TikTokPublishOptions",
        "ShopifyPublishOptions",
        "publish_preflight_rejected",
        "publish_preflight_unavailable",
    ]:
        assert token in generated

    assert "receipt: components[\"schemas\"][\"PublishReceiptV1\"]" in generated
    assert (
        "platform_options: components[\"schemas\"][\"TikTokPublishOptions\"]"
        " | components[\"schemas\"][\"ShopifyPublishOptions\"]"
    ) in generated
