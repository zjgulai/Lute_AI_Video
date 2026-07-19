---
title: Tenant-Scoped Submit Idempotency Implementation Plan
doc_type: workflow
module: submission
topic: tenant-scoped-submit-idempotency
status: stable
created: 2026-07-12
updated: 2026-07-20
owner: self
source: human+ai
---

# Tenant-Scoped Submit Idempotency Implementation Plan

**Approved design:** `docs/superpowers/specs/2026-07-12-tenant-scoped-submit-idempotency-design.md`

**Roadmap scope:** W1-13, W1-15, W1-16.

**Branch:** `codex/enterprise-ai-content-closure-20260711`

**Execution boundary:** Local code, fake-provider tests, disposable SQLite/PostgreSQL 18, static checks, frontend build, and UI-only fake-route E2E only. `production unchanged`, `provider_call=false`, no production migration, deploy, publish, or delivery.

## Completion criteria

- [x] Canonical async Fast and S1-S5 submits require a valid `Idempotency-Key` header.
- [x] Same tenant/key/canonical payload returns the original job and creates exactly one execution owner.
- [x] Same tenant/key with changed payload, operation, scenario, or effective policy returns `409` before downstream work.
- [x] Different tenants may reuse the same raw key without visibility or conflict leakage.
- [x] PostgreSQL and SQLite claims are atomic under concurrent requests.
- [x] Fast identity, status, safe terminal result, and stale-owner truth are durable.
- [x] Scenario claim occurs before S1/S3 translation, state creation, and background task registration.
- [x] Ambiguous browser responses recover through GET readback; no automatic second POST or replacement key occurs.
- [x] Repository/app reconstruction preserves original-job identity; stale nonterminal work becomes `recovery_required`, not a duplicate execution.
- [x] Raw keys never reach server persistence/logs/URLs/responses; request/provider credentials never enter fingerprints or pending browser payloads.
- [x] Focused tests, disposable PG18 verification, full backend/frontend gates, diff/secret checks, and independent security/spec review pass.
- [x] Roadmap, API reference, runbooks, OpenAPI types, SDD reports, and planning records match verified behavior.

## Task 1 — Freeze RED contract tests

**Files:**

- Create `tests/test_submission_idempotency_contract.py`.
- Create `web/src/lib/idempotentSubmission.test.ts`.
- Extend `tests/test_scenario_generation_safety_policy.py` only where the shared submit-surface matrix needs mandatory headers.
- Extend `web/src/components/apiFetchErrorNormalization.test.ts` only for idempotency/readback transport semantics.

**RED assertions:**

- Header validation: missing, duplicate, short, oversized, whitespace/control characters; body `idempotency_key` remains `422`.
- Canonical hashing: key order/default normalization, list order, strict types, policy version, and `api_keys` exclusion.
- Claim outcomes: owner, replay, conflict, cross-tenant independence, terminal CAS protection.
- Browser: persist before POST, stable key reuse, ambiguous-error classification, bounded GET readback, no second mutation, reload recovery, `409` handling.

**Gate:** New tests fail for missing behavior, not import/setup mistakes.

## Task 2 — Add schema and atomic repository

**Files:**

- Create one Alembic revision descending from `7c4b8e2f1a09`.
- Update `src/storage/migrations/001_init.sql`.
- Update `src/storage/db.py` SQLite initialization and required-table verification.
- Create `src/storage/idempotency_repository.py`.
- Update `src/storage/__init__.py` only if repository exports are required.
- Add schema/repository coverage to `tests/test_submission_idempotency_contract.py` and the existing schema-contract suites.

**Implementation:**

- Add `idempotency_records` with tenant/key and tenant/resource unique constraints, lifecycle checks, safe response/result projections, owner lease, and timestamps.
- Implement PG `INSERT ... ON CONFLICT DO NOTHING RETURNING` owner arbitration.
- Implement SQLite `BEGIN IMMEDIATE` plus `INSERT OR IGNORE` under the existing SQLite lock.
- Implement compare-and-set transition, lookup, DB-time lease renewal, and expired-lease reconciliation.
- Production explicitly requires healthy PG/table and raises a typed store-unavailable error; development/test may use SQLite.

**GREEN gate:** Repository unit/concurrency/reconstruction tests pass; no router/task integration yet.

## Task 3 — Add shared submit-idempotency service and readback API

**Files:**

- Create `src/services/submission_idempotency.py`.
- Create `src/routers/submissions.py`.
- Update `src/api.py` router registration and CORS allowlist.
- Add HTTP/readback/CORS coverage to `tests/test_submission_idempotency_contract.py`.

**Implementation:**

- Validate a single 16-128 character header without logging/echoing it.
- Build `submit-fingerprint.v1` from validated request plus effective policy while excluding credentials.
- Preallocate stable resource identity and a truthful `reserved` projection.
- Expose claim/replay/conflict/store-unavailable mapping and stable error codes.
- Add authenticated `GET /submissions/idempotency`; unknown and cross-tenant both return `404`.
- Add independent heartbeat handles using DB time: 120-second lease, 30-second renewal, terminal/graceful-shutdown CAS ordering.

**GREEN gate:** Pure service, header, readback, CORS, heartbeat, and failure-boundary tests pass.

## Task 4 — Integrate Fast Mode durable jobs

**Files:**

- Update `src/routers/scenario.py` Fast submit/status paths.
- Update `src/tasks/fast_task_registry.py`.
- Extend `tests/test_fast_mode_async.py` and `tests/test_submission_idempotency_contract.py`.

**Implementation:**

- Validate/claim before `_inject_api_keys`, service lookup, or `asyncio.create_task`.
- Pass a preallocated `task_id`; keep only live task handles in memory.
- Persist queued/running stage, safe failure, and allowlisted terminal result to the ledger.
- Make status tenant-bound through durable records and return `recovery_required` after a stale lease.
- Ensure same-key concurrent/replay paths call `create_task` and `FastModeService.generate` exactly once.

**GREEN gate:** Fast owner/replay/conflict/status/result/restart tests pass with a fake service and zero provider calls.

## Task 5 — Integrate S1-S5 canonical async submit

**Files:**

- Update `src/routers/scenario.py` unified submit path.
- Extend `tests/test_submission_idempotency_contract.py` and scenario router/generation-policy suites where necessary.

**Implementation:**

- Validate request and effective policy, then claim before `_inject_api_keys`, S1/S3 translation, `StepRunner.init_state`, or background registration.
- Pass the preallocated label to `init_state`.
- Replay returns the original label/current submission state without re-entering translation or pipeline setup.
- Background wrapper renews the lease and projects terminal/failure truth into the ledger.
- Readback reconciles already terminal tenant-owned scenario state; stale nonterminal state becomes `recovery_required` without automatic resume.

**GREEN gate:** Parameterized S1-S5 same/different payload, cross-tenant, concurrency, translator-count, state-count, and restart tests pass.

## Task 6 — Implement frontend persistence and recovery library

**Files:**

- Create `web/src/lib/idempotentSubmission.ts`.
- Update `web/src/components/api.ts`.
- Update `web/src/stores/usePipelineStore.ts` and `web/src/stores/persistence.ts`.
- Extend/create store/API/library tests.

**Implementation:**

- Require `idempotencyKey` in `submitScenario` and `submitFastMode` options.
- Add `getSubmissionByIdempotencyKey` using authenticated GET and the header.
- Add a short async-submit timeout independent of long blocking routes.
- Upgrade persisted state with minimal pending submissions; store no request body or credential.
- Implement key generation, pre-fetch persistence, error classification, 0/1/2/5-second readback, resource binding, unknown preservation, and explicit abandonment.
- Stay on idempotency readback for `reserved/initializing`; switch to resource status only at `queued/running/terminal`.

**GREEN gate:** Library/API/store tests prove no blind POST retry and safe reload behavior.

## Task 7 — Wire Scenario and Fast UI recovery

**Files:**

- Update `web/src/app/page.tsx`.
- Update `web/src/components/FastModePanel.tsx`.
- Update `web/src/components/StageProgress.tsx` and `web/src/components/PipelineStatusBar.tsx` only for recovery/terminal consistency.
- Update i18n strings and focused component/page tests.

**Implementation:**

- Route both scenario start handlers through the shared orchestration helper.
- Restore pending/active Scenario and Fast work after hydration without a mutation POST.
- Render confirming, unknown, conflict, and `recovery_required` states truthfully.
- Provide continue-query and confirmed-abandon actions.
- Change cancel wording so browser abort/hide does not claim server cancellation.
- Treat `completed`, `completed_bounded`, and `completed_full` consistently as terminal.

**GREEN gate:** Focused Vitest and UI-only fake-route E2E pass; submit count remains exactly one.

## Task 8 — Synchronize contracts and repository callers

**Files:**

- Update `docs/reference/api-endpoints.md` and a focused idempotency runbook.
- Update production/UI-only Playwright specs that directly call canonical async submit.
- Regenerate `web/src/types/api.generated.ts` through the project command.
- Update route/auth/token-smoke contract fixtures without raising submit/retry caps.
- Update backup/schema table-set expectations affected by the additive table.

**Gate:** OpenAPI/typegen, contract tests, docs/link checks, and token-smoke static guards pass. No token smoke executes.

## Task 9 — Disposable database and full acceptance

**Execution:**

- Run isolated SQLite persistence/concurrency tests.
- Start disposable PostgreSQL 18, apply migration upgrade, exercise concurrent claims/CAS/reconstruction, downgrade, and verify fresh-init parity.
- Run focused backend suites and Ruff.
- Run full `make ci`.
- Run focused and full frontend Vitest, ESLint, TypeScript, and Next production build.
- Run UI-only fake-route Playwright where browser runtime is available; never target production mutation paths.
- Run `git diff --check`, changed-file secret scan, and inspect the complete unstaged diff.
- Request independent spec/security review; resolve all Critical/Important findings.

**Acceptance:** Record exact commands/results and retain the evidence ceiling `L2-fixture-or-dry-run`.

## Task 10 — State synchronization and handoff

**Files:**

- Update `docs/workflows/enterprise-ai-content-all-scenarios-roadmap-20260711.md` only from verified evidence.
- Update the tracked roadmap, submission-idempotency recovery runbook, and `AGENTS.md` from fresh evidence.
- Update long-lived project guidance only if implementation changes a durable architecture fact.

**Final truth:**

- W1-13 becomes complete only when browser ambiguous readback tests pass.
- W1-15 becomes complete only when same/different payload and tenant isolation pass.
- W1-16 becomes complete only when durable concurrency/restart contracts pass.
- Full worker resume, cost/budget, provider retry, production migration/deploy, provider generation, publish, and delivery remain separate work.
