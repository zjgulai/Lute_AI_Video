---
title: "W5 No-Provider Acceptance Harness Implementation Plan"
doc_type: workflow
module: acceptance
topic: no-provider-acceptance-harness
status: stable
created: 2026-07-23
updated: 2026-07-23
owner: self
source: human+ai
---

# W5 No-Provider Acceptance Harness Implementation Plan

> **For Codex:** Execute this plan in strict RED -> GREEN -> focused regression -> full local gate -> independent six-dimension review cycles. This batch is local L2 evidence only.

**Goal:** Close W5-01 through W5-03 with a parameterized Fast/S1-S5 no-provider acceptance contract, a single-submit L4 draft-plan generator, and strict HU-03 plus scenario-specific human-review records without creating provider or execution authority.

**Architecture:** Add one pure domain module that projects canonical scenario definitions from existing step/provenance SSOTs, validates exact draft constraints, and builds immutable human-review records. Add one local CLI that creates draft packets only under `tmp/` or outside the repository. Do not change submit routes, `GenerationExecutionProfile` resolution, provider clients, production deployment, publish, delivery, or acceptance consumption.

**Evidence ceiling:** L2 local/static/fixture. W5-04 through W5-12 remain blocked external. A generated draft is not an approval, provider budget authorization, persisted execution profile, acceptance record, or permission to retry.

## Safety invariants

- `execution_authorized=false` and `provider_calls_allowed=false` are literals.
- `status=draft_pending_human_review`; this module has no approve or execute transition.
- `submission_cap=1`, `automatic_retry_cap=0`, and `provider_max_retries=0` are literals.
- Artifact disposition is exactly `pending_review`; publish and delivery remain false.
- Tenant, scenario, sample, timestamps, evidence refs, budget nanos, and job caps validate strictly.
- S1-S5 step order comes from `SCENARIO_STEP_ORDERS`; provenance coverage comes from `PRODUCER_SPECS`.
- Fast has a separate explicit contract and never impersonates StepRunner provenance.
- No API key, environment lookup, network library, provider client, production URL, or HTTP mutation exists in this batch.
- The CLI writes only to `tmp/` or outside the repository and refuses overwrite by default.

## Task 1: Parameterized no-provider contract

**Files:**

- Create: `tests/test_w5_acceptance_harness.py`
- Create: `src/pipeline/w5_acceptance_harness.py`

**RED:** Add parameterized Fast/S1-S5 tests proving every contract contains tenant isolation, exact safety policy, canonical step order, pending-review artifact disposition, audit truth, transparency truth, and exact human gates. Prove S1-S5 step/provenance drift fails validation and Fast remains distinct.

**GREEN:** Add strict frozen contract models and a code-owned registry. Import the S1-S5 step order and verify producer parity at projection time. Define Fast text/media/pending-review requirements explicitly.

**Verify:**

```bash
.venv/bin/python -m pytest -q tests/test_w5_acceptance_harness.py
.venv/bin/python -m ruff check src/pipeline/w5_acceptance_harness.py tests/test_w5_acceptance_harness.py
```

## Task 2: Non-authorizing L4 draft-plan generator

**Files:**

- Modify: `tests/test_w5_acceptance_harness.py`
- Modify: `src/pipeline/w5_acceptance_harness.py`

**RED:** Prove each scenario binds one tenant/sample, a positive exact integer USD-nanos ceiling, explicit finite job caps, single submit, zero retry, pending-review-only disposition, canonical steps, required review gates, audit/transparency checks, and stable stop conditions. Reject bool/float/zero/overflow money, unknown cap categories, missing/extra caps, forged authority/status fields, unsafe refs, and timestamp inversions.

**GREEN:** Add a strict frozen `W5ScenarioPlanDraftV1` and pure builder. Derive the plan identifier from canonical secret-free fields. Keep `execution_authorized`, `provider_calls_allowed`, `publish_allowed`, and `delivery_accepted` false. Emit only a future full-media expectation, never a runtime `GenerationExecutionProfile`.

**Verify:** focused test plus Ruff and source Pyright.

## Task 3: HU-03 and scenario-specific review records

**Files:**

- Modify: `tests/test_w5_acceptance_harness.py`
- Modify: `src/pipeline/w5_acceptance_harness.py`

**RED:** Prove HU-03 contains exactly the four canonical criteria and one `pass|revise|reject` outcome with a short reason. Prove S1 requires Gate, S2 brand review, S3 rights/source review, S4 footage ownership, S5 model/product review, while Fast requires pending-review acceptance. Reject cross-tenant/scenario/sample records, duplicate/missing gates, blank reviewers/reasons/evidence refs, naive/out-of-window timestamps, and pass decisions with failed criteria.

**GREEN:** Add immutable strict review models plus packet validation. A structurally valid record is still only recorded human evidence; it does not promote an artifact, authorize a provider, or grant publish/delivery authority.

**Verify:** focused test plus Ruff and source Pyright.

## Task 4: Safe local packet CLI and script governance

**Files:**

- Create: `scripts/build_w5_acceptance_plan.py`
- Create: `tests/test_build_w5_acceptance_plan.py`
- Modify: `configs/scripts-governance-contract.json`
- Modify: `docs/runbooks/scripts-governance.md`

**RED:** Prove the CLI creates deterministic draft JSON, prints JSON without writing by default, allows output only under `tmp/` or outside the repository, refuses overwrite without `--force`, uses stable exit code 2 for bad inputs, and never imports/calls network or provider modules.

**GREEN:** Implement a small argparse wrapper around the pure builder. Require explicit scenario, tenant, sample, budget nanos, creation/expiry timestamps, and job-cap JSON. Keep human record creation in the domain API/tests; the CLI only creates a plan draft and contract snapshot.

**Verify:** CLI tests and `tests/test_scripts_governance.py`.

## Task 5: Documentation and state synchronization

**Files:**

- Modify: `docs/workflows/enterprise-ai-content-all-scenarios-roadmap-20260711.md`
- Modify: `AGENTS.md`
- Modify: `.kiro/plan/task_plan.md`
- Modify: `.kiro/plan/progress.md`
- Modify: `.kiro/plan/findings.md`

**GREEN:** Mark only W5-01 through W5-03 as locally complete after tests and independent approval. State explicitly that W5-04 through W5-12 remain external and that no provider, production, publish, delivery, GitHub, stage, or commit action occurred.

## Task 6: Full local verification and independent review loop

**Main-thread verification:**

```bash
.venv/bin/python -m pytest -q tests/test_w5_acceptance_harness.py tests/test_build_w5_acceptance_plan.py tests/test_scripts_governance.py
.venv/bin/python -m pytest -q tests/test_generation_policy_step_guard.py tests/test_scenario_completion_truth.py tests/test_transparency_provenance.py
.venv/bin/python -m ruff check src tests scripts
.venv/bin/pyright src
make ci
git diff --check
```

Also run a scoped strong-secret scan over this batch's files and confirm the Git index remains unstaged.

**Independent review:** Hand the exact change set and evidence to the same read-only reviewer. Require findings across requirements completeness, logic correctness, edge cases, code quality, test coverage, and actual runtime results. The reviewer must not edit code.

**Repair loop:** Main thread accepts/rejects each finding with evidence, adds RED tests for accepted defects, fixes them, reruns proportional gates, then asks the same reviewer to reverify. Repeat until `PASS / APPROVE` with `accepted_actionable_findings=0`, or report the exact blocker.
