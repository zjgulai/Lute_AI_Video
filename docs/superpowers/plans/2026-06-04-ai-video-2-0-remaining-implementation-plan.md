---
title: AI Video 2.0 Remaining Implementation Plan
doc_type: workflow
module: ai-video-2.0
topic: remaining-implementation-plan
status: review
created: 2026-06-04
updated: 2026-06-04
owner: self
source: human+ai
---

# AI Video 2.0 Remaining Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the unimplemented AI Video 2.0 surfaces after C14 so the project has a full dry-run commercial video operating layer before any authorized live provider smoke.

**Architecture:** Keep the pipeline evidence-bounded. C15-C20 expose and package existing dry-run capabilities through API, UI, benchmark, brand-review, and longform audit surfaces. C21 is the only milestone allowed to approach `L4-authorized-live`, and only after explicit user approval plus approval-record checks.

**Tech Stack:** Python 3.11+/Pydantic V2/FastAPI/pytest/ruff, Next.js 16/React 19/TypeScript/Vitest, existing `QualityContract`, `RuntimePromptPreviewResult`, `PromptPreviewAuditBundle`, `BrandConstraintBundle`, and longform contract models.

---

## Current Baseline

Completed and committed:

- C1-C5 commercial contracts, offline gates, provider signal registry, prompt compiler, production job ledger.
- C6-C8 scenario injection projection, UI read-only panels, longform contracts/gates, quality/job/diff panels.
- C9 no-token preflight and authorized-live harness guard.
- C10 candidate brand token intake and explicit review boundary.
- C11 runtime injection executor.
- C12 runtime prompt dry-run preview.
- C13 prompt preview quality gate.
- C14 prompt preview audit bundle.

Current maximum supported evidence level for C1-C20 remains `L2-fixture-or-dry-run`.

Forbidden until C21 approval:

- No provider call.
- No token smoke.
- No delivery acceptance.
- No publish allowed.
- No customer evidence claim.
- No commercial production-ready claim.

---

## File Responsibility Map

Planned new files:

- `src/pipeline/prompt_preview_audit_workflow.py`
  Build a single dry-run workflow from compile input, runtime injection, quality contract, and prompt-preview audit bundle.

- `tests/test_prompt_preview_audit_workflow.py`
  Verify workflow success/blocking paths and no prompt or brand payload leakage.

- `web/src/components/PromptPreviewAuditPanel.tsx`
  Render the sanitized prompt-preview audit bundle in the product control surface.

- `web/src/components/PromptPreviewAuditPanel.test.tsx`
  Verify UI states for `blocked` and `allowed-with-label`.

- `src/pipeline/brand_review_audit_bundle.py`
  Package candidate ledger + explicit review report + generated bundle into an evidence-bounded brand review audit object.

- `tests/test_brand_review_audit_bundle.py`
  Verify candidate-only, partially approved, and rejected review audit boundaries.

- `src/pipeline/longform_audit_bundle.py`
  Package S3/S4 longform contracts and gate output into a reusable dry-run longform audit bundle.

- `tests/test_longform_audit_bundle.py`
  Verify source rights, timeline, EDL, caption safe-zone, and no delivery acceptance behavior.

- `scripts/no_token_commercial_benchmark.py`
  Generate a dry-run benchmark report from fixtures without provider calls.

- `tests/test_no_token_commercial_benchmark.py`
  Verify benchmark blocks missing evidence and emits L2-only status.

Planned modified files:

- `src/routers/scenario.py`
  Add a read-only prompt-preview audit endpoint after workflow module exists.

- `web/src/components/api.ts` and `web/src/types/api.generated.ts`
  Add or regenerate frontend types only if OpenAPI drift is real.

- `web/src/components/StepByStepView.tsx` and/or `StageProgress.tsx`
  Show prompt-preview audit bundle summary without action buttons.

- `docs/claude/known-gaps-stable.md` or a current 2.0 status doc
  Update only after verification, and keep evidence labels explicit.

---

## C15: Prompt Preview Audit Workflow And API

**Purpose:** Make C12-C14 consumable through a single backend workflow and a read-only scenario endpoint.

### Commit 15.1: Workflow object

**Files:**

- Create: `src/pipeline/prompt_preview_audit_workflow.py`
- Test: `tests/test_prompt_preview_audit_workflow.py`

- [ ] **Step 1: Write failing tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_prompt_preview_audit_workflow.py -q
```

Expected before implementation: import or function missing.

Required tests:

```python
def test_prompt_preview_audit_workflow_returns_allowed_with_label_bundle():
    bundle = build_prompt_preview_audit_workflow(
        contract=_quality_contract(),
        compile_input=_compile_input(bundle=_bundle(["bat_hard_fixture"])),
        runtime_injection=_runtime_injection(["bat_hard_fixture"]),
        planned_injection={"hard_token_ids": ["bat_hard_fixture"], "soft_token_ids": []},
    )

    assert bundle.evidence_boundary.decision == "allowed-with-label"
    assert bundle.gate_decision.status == "review_required"
    assert bundle.delivery_accepted is False
    assert bundle.publish_allowed is False
    assert bundle.prompt_hash is not None


def test_prompt_preview_audit_workflow_blocks_runtime_mismatch_without_compiling_provider():
    bundle = build_prompt_preview_audit_workflow(
        contract=_quality_contract(),
        compile_input=_compile_input(bundle=_bundle(["bat_compile"])),
        runtime_injection=_runtime_injection(["bat_runtime"]),
        planned_injection={"hard_token_ids": ["bat_runtime"], "soft_token_ids": []},
    )

    assert bundle.evidence_boundary.decision == "blocked"
    assert "runtime_prompt_injection_diff_pass" in [
        action.check for action in bundle.repair_plan.actions
    ]
```

- [ ] **Step 2: Implement workflow**

Implementation shape:

```python
from collections.abc import Mapping
from typing import Any

from src.models.commercial_contracts import PromptCompileInput, QualityContract
from src.pipeline.runtime_injection_executor import RuntimeInjectionResult
from src.pipeline.runtime_prompt_preview import build_runtime_prompt_preview
from src.quality.prompt_preview_audit_bundle import (
    PromptPreviewAuditBundle,
    build_prompt_preview_audit_bundle,
)


def build_prompt_preview_audit_workflow(
    *,
    contract: QualityContract,
    compile_input: PromptCompileInput,
    runtime_injection: RuntimeInjectionResult | Mapping[str, Any],
    planned_injection: Mapping[str, Any] | None = None,
) -> PromptPreviewAuditBundle:
    preview = build_runtime_prompt_preview(
        compile_input=compile_input,
        runtime_injection=runtime_injection,
        planned_injection=planned_injection,
    )
    return build_prompt_preview_audit_bundle(contract=contract, preview=preview)
```

- [ ] **Step 3: Verify**

Run:

```bash
.venv/bin/python -m pytest tests/test_prompt_preview_audit_workflow.py tests/test_runtime_prompt_preview.py tests/test_prompt_preview_audit_bundle.py
.venv/bin/python -m ruff check src/pipeline/prompt_preview_audit_workflow.py tests/test_prompt_preview_audit_workflow.py
git diff --check
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add src/pipeline/prompt_preview_audit_workflow.py tests/test_prompt_preview_audit_workflow.py
git commit -m "feat: 增加prompt预览审计工作流"
```

### Commit 15.2: Backend read-only endpoint

**Files:**

- Modify: `src/routers/scenario.py`
- Test: `tests/test_prompt_preview_audit_router.py`

- [ ] **Step 1: Add request model and endpoint**

Endpoint:

```text
POST /scenario/{scenario}/prompt-preview/audit
```

Request body fields:

- `contract`: `QualityContract` payload.
- `compile_input`: `PromptCompileInput` payload.
- `runtime_injection`: `RuntimeInjectionResult` payload.
- `planned_injection`: optional sanitized plan payload.

Rules:

- `scenario` path must match `contract.scenario`, `compile_input.scenario`, and `runtime_injection.scenario`.
- Response is `PromptPreviewAuditBundle.model_dump(mode="json")`.
- Response must not include `prompt`, `negative_prompt`, token `payload`, token `payload_summary`, or brand asset source body.

- [ ] **Step 2: Write tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_prompt_preview_audit_router.py -q
```

Expected before implementation: route missing.

Required assertions:

- `200` for valid dry-run request.
- `422` for scenario mismatch.
- response has `evidence_boundary.evidence_level == "L2-fixture-or-dry-run"`.
- serialized response excludes `must-not-leak`, `prompt`, `negative_prompt`.

- [ ] **Step 3: Verify**

Run:

```bash
.venv/bin/python -m pytest tests/test_prompt_preview_audit_router.py tests/test_scenario_commercial_injection_router.py
.venv/bin/python -m ruff check src/routers/scenario.py tests/test_prompt_preview_audit_router.py
git diff --check
```

- [ ] **Step 4: Commit**

```bash
git add src/routers/scenario.py tests/test_prompt_preview_audit_router.py
git commit -m "feat: 暴露prompt预览审计只读接口"
```

### Commit 15.3: OpenAPI drift

Run:

```bash
.venv/bin/python scripts/check_openapi_types_drift.py
```

If frontend generated types drift:

```bash
git add web/src/types/api.generated.ts
git commit -m "chore: 同步prompt预览审计接口类型"
```

If no drift, do not commit.

---

## C16: Prompt Preview Audit UI

**Purpose:** Show the audit bundle in the UI without edit, publish, or generate actions.

### Commit 16.1: Panel component

**Files:**

- Create: `web/src/components/PromptPreviewAuditPanel.tsx`
- Test: `web/src/components/PromptPreviewAuditPanel.test.tsx`

Panel behavior:

- `blocked`: show blocker count, repair actions, forbidden claims.
- `allowed-with-label`: show prompt hash, provider/model, human-review requirement, forbidden claims.
- Never show prompt body.
- No action buttons.

Verify:

```bash
cd web && npm test -- PromptPreviewAuditPanel.test.tsx
cd web && npm run lint
cd web && npx tsc --noEmit -p tsconfig.json
git diff --check
```

Commit:

```bash
git add web/src/components/PromptPreviewAuditPanel.tsx web/src/components/PromptPreviewAuditPanel.test.tsx
git commit -m "feat: 展示prompt预览审计包"
```

### Commit 16.2: Attach panel to step surfaces

**Files:**

- Modify: `web/src/components/StepByStepView.tsx`
- Modify: `web/src/components/StageProgress.tsx` only if current-step summary has a stable data path.
- Test: existing component tests plus new assertions.

Verify:

```bash
cd web && npm test -- StepByStepView.test.tsx StageProgress.test.tsx PromptPreviewAuditPanel.test.tsx
cd web && npm run lint
cd web && npx tsc --noEmit -p tsconfig.json
git diff --check
```

Commit:

```bash
git add web/src/components/StepByStepView.tsx web/src/components/StageProgress.tsx web/src/components/*.test.tsx
git commit -m "feat: 接入prompt预览审计只读面板"
```

---

## C17: Brand Review Audit Bundle

**Purpose:** Make brand token review explainable before any reviewed tokens are used by runtime injection.

### Commit 17.1: Brand review audit object

**Files:**

- Create: `src/pipeline/brand_review_audit_bundle.py`
- Test: `tests/test_brand_review_audit_bundle.py`

Object fields:

- `audit_bundle_id`
- `brand_id`
- `source_ledger_status`
- `approved_token_count`
- `rejected_token_ids`
- `skipped_token_ids`
- `evidence_level = "L2-fixture-or-dry-run"`
- `approved_for_runtime_injection: bool`
- `forbidden_claims`
- `next_evidence`

Rules:

- Candidate ledger alone always returns `approved_for_runtime_injection = False`.
- Explicit review report with at least one approved generation-scoped token can return `True`.
- Never include token `payload`.

Verify:

```bash
.venv/bin/python -m pytest tests/test_brand_review_audit_bundle.py tests/test_brand_token_intake.py tests/test_brand_token_review.py
.venv/bin/python -m ruff check src/pipeline/brand_review_audit_bundle.py tests/test_brand_review_audit_bundle.py
git diff --check
```

Commit:

```bash
git add src/pipeline/brand_review_audit_bundle.py tests/test_brand_review_audit_bundle.py
git commit -m "feat: 增加品牌token审核审计包"
```

### Commit 17.2: Brand review CLI dry-run

**Files:**

- Modify or create: `scripts/brand_review_audit.py`
- Test: `tests/test_brand_review_audit_cli.py`

Rules:

- Reads candidate ledger and optional explicit review decision JSON.
- Defaults to blocked/candidate-only when decisions are absent.
- Writes report to stdout or `tmp/outputs/` when `--output` is provided.
- No provider call.

Verify:

```bash
.venv/bin/python -m pytest tests/test_brand_review_audit_cli.py
.venv/bin/python -m ruff check scripts/brand_review_audit.py tests/test_brand_review_audit_cli.py
git diff --check
```

Commit:

```bash
git add scripts/brand_review_audit.py tests/test_brand_review_audit_cli.py
git commit -m "feat: 增加品牌token审核dry-run CLI"
```

---

## C18: Longform Audit Bundle For S3/S4

**Purpose:** Package longform production gates into reusable evidence bundles before implementation reaches real long-video production.

### Commit 18.1: Longform audit bundle

**Files:**

- Create: `src/pipeline/longform_audit_bundle.py`
- Test: `tests/test_longform_audit_bundle.py`

Bundle inputs:

- `LongformProductionContract`
- `QualityContract`
- `AuditEvidenceBundle`

Required behavior:

- 90s+ without timeline blocks stays blocked.
- 300s single-shot stays blocked.
- Missing source rights, source fingerprint, EDL, caption safe-zone evidence stays blocked.
- Passing longform gate returns `review_required`, not delivery accepted.

Verify:

```bash
.venv/bin/python -m pytest tests/test_longform_audit_bundle.py tests/test_commercial_contracts.py tests/test_commercial_gate.py
.venv/bin/python -m ruff check src/pipeline/longform_audit_bundle.py tests/test_longform_audit_bundle.py
git diff --check
```

Commit:

```bash
git add src/pipeline/longform_audit_bundle.py tests/test_longform_audit_bundle.py
git commit -m "feat: 增加长视频生产审计包"
```

### Commit 18.2: S3/S4 fixture benchmark cases

**Files:**

- Add: `tests/fixtures/commercial_video/longform_audit_bundle_cases.json`
- Modify: `tests/test_longform_audit_bundle.py`

Cases:

- `s3_missing_source_rights_blocks`
- `s3_missing_timeline_edl_blocks`
- `s4_missing_footage_rights_blocks`
- `s4_caption_safe_zone_violation_blocks`
- `s4_ready_for_human_review_not_publish`

Verify and commit:

```bash
.venv/bin/python -m pytest tests/test_longform_audit_bundle.py
git diff --check
git add tests/fixtures/commercial_video/longform_audit_bundle_cases.json tests/test_longform_audit_bundle.py
git commit -m "test: 增加长视频审计包fixture覆盖"
```

---

## C19: No-Token Commercial Benchmark Report

**Purpose:** Produce a repeatable L2 benchmark report across brand token review, runtime injection, prompt preview, gate, job ledger, and longform audit.

### Commit 19.1: Benchmark script

**Files:**

- Create: `scripts/no_token_commercial_benchmark.py`
- Test: `tests/test_no_token_commercial_benchmark.py`

Report fields:

- `benchmark_id`
- `evidence_level = "L2-fixture-or-dry-run"`
- `provider_calls_made = false`
- `authorized_live = false`
- `checks`
- `blocked_count`
- `review_required_count`
- `forbidden_claims`

Verify:

```bash
.venv/bin/python -m pytest tests/test_no_token_commercial_benchmark.py
.venv/bin/python -m ruff check scripts/no_token_commercial_benchmark.py tests/test_no_token_commercial_benchmark.py
git diff --check
```

Commit:

```bash
git add scripts/no_token_commercial_benchmark.py tests/test_no_token_commercial_benchmark.py
git commit -m "feat: 增加无token商业视频benchmark报告"
```

### Commit 19.2: Benchmark evidence docs

**Files:**

- Modify: `docs/claude/known-gaps-stable.md` or current 2.0 status document.

Rules:

- Add only verified commands and outputs from C19.
- Label as `L2-fixture-or-dry-run`.
- Do not write `production-ready`, `validated`, or `commercial delivery complete`.

Verify:

```bash
git diff --check
```

Commit:

```bash
git add docs/claude/known-gaps-stable.md
git commit -m "docs: 更新2.0无tokenbenchmark证据边界"
```

---

## C20: API/UI Acceptance Sweep

**Purpose:** Make the 2.0 dry-run toolchain visible and testable as a product control surface.

### Commit 20.1: Backend acceptance sweep

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_brand_token_intake.py \
  tests/test_brand_token_review.py \
  tests/test_brand_review_audit_bundle.py \
  tests/test_runtime_injection_executor.py \
  tests/test_runtime_prompt_preview.py \
  tests/test_prompt_preview_audit_bundle.py \
  tests/test_prompt_preview_audit_workflow.py \
  tests/test_prompt_preview_audit_router.py \
  tests/test_longform_audit_bundle.py \
  tests/test_no_token_commercial_benchmark.py \
  tests/test_commercial_gate.py \
  tests/test_production_job_ledger.py
.venv/bin/python -m ruff check src tests scripts
.venv/bin/python scripts/check_openapi_types_drift.py
git diff --check
```

Commit only if status docs change:

```bash
git add docs/claude/known-gaps-stable.md
git commit -m "docs: 更新AI视频2.0 dry-run验收状态"
```

### Commit 20.2: Frontend acceptance sweep

Run:

```bash
cd web && npm run lint
cd web && npx tsc --noEmit -p tsconfig.json
cd web && npm test
```

Commit only if UI docs or generated types change.

---

## C21: Authorized-Live Readiness, Still Disabled By Default

**Purpose:** Prepare the project to run a tiny authorized token smoke later, without running it now.

### Commit 21.1: Approval record gate hardening

**Files:**

- Modify: existing authorized-live harness or preflight script.
- Test: existing C9 tests plus new approval-record tests.

Rules:

- Requires `RUN_TOKEN_SMOKE=1`.
- Requires explicit approval record path.
- Requires provider capability evidence.
- Requires audit bundle readiness.
- Default execution remains dry-run.

Verify:

```bash
.venv/bin/python -m pytest tests/test_token_smoke_preflight.py tests/test_authorized_live_harness.py
.venv/bin/python -m ruff check scripts tests/test_token_smoke_preflight.py tests/test_authorized_live_harness.py
git diff --check
```

Commit:

```bash
git add scripts tests/test_token_smoke_preflight.py tests/test_authorized_live_harness.py
git commit -m "feat: 加强授权真实生成审批记录门禁"
```

### Commit 21.2: User approval checkpoint

Stop before running any live provider test.

Required user statement:

```text
我明确授权 C21 运行一次真实 token smoke，允许调用 provider，使用的 provider/model 是 <provider>/<model>，预算上限是 <amount>。
```

Without that statement, C21 remains blocked.

---

## C22: Final 2.0 Self-Proof Pack

**Purpose:** Produce a concise status pack after C15-C21, with exact evidence grade labels.

**Files:**

- Modify current 2.0 status doc or create one under `docs/workflows/` if no current status doc can carry the result.

Required sections:

- Completed commits C1-C21.
- Current evidence grade.
- Supported claims.
- Forbidden claims.
- Known blockers.
- Next evidence needed for `L4-authorized-live`.

Verify:

```bash
git diff --check
```

Commit:

```bash
git add docs/workflows/<selected-status-doc>.md
git commit -m "docs: 固化AI视频2.0最终自证状态"
```

---

## Recommended Next Execution Order

1. C15.1 workflow object.
2. C15.2 backend endpoint.
3. C15.3 OpenAPI drift.
4. C16.1 UI panel.
5. C16.2 UI integration.
6. C17 brand review audit.
7. C18 longform audit bundle.
8. C19 benchmark.
9. C20 acceptance sweep.
10. C21 only after explicit live approval.
11. C22 final self-proof pack.

This order keeps every step testable and prevents product/UI work from depending on unproven live-provider behavior.
