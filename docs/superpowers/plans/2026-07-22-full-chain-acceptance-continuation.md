# Full-Chain Acceptance Continuation Implementation Plan

> **For Codex:** Execute this plan in strict RED -> GREEN -> focused regression -> independent six-dimension review cycles. Do not push GitHub, call a provider, publish, deliver, or deploy an unproven local SHA.

**Goal:** Close the remaining enterprise acceptance scope without promoting provider-off or bounded evidence into full-chain success, starting with W2 lifecycle truth and then progressing through the tracked W2-W6 roadmap.

**Architecture:** Preserve the current server-owned request policy, provider-cost ledger, idempotency ledger, acceptance records, and immutable deployment wrapper. Add one canonical scenario lifecycle derivation boundary that consumes persisted step/artifact/error truth; all API, durable readback, wrapper results, and frontend classification must use a coherent envelope. A full execution profile remains server-owned and cannot be inferred from client input or from budget authorization alone. Real provider, publish, delivery, notification, infrastructure, and owner-signoff actions remain individually authorized L4 gates.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, LangGraph/StepRunner, PostgreSQL/SQLite persistence, Next.js 16, React 19, TypeScript, Vitest, pytest, Playwright, Docker deployment wrapper.

**Evidence ceiling for this plan before external authorization:** L2 local/fixture/disposable database. Existing production evidence remains L3 read-only for SHA `6916f170827665407bf992a0987fa095c7fa1bf6`.

---

## Program order and release gates

1. **W2 runtime truth:** W2-01-W2-04 first, followed by W2-05-W2-17 in independently reviewable batches.
2. **W3 operations:** local reproducibility, type, observability, backup-manifest and recovery work; W3-08 notifications, W3-12/W3-13 external storage/KMS/host-loss, and W3-17 GitHub environments remain blocked until separately authorized.
3. **W4 transparency:** local policy, sidecar, label, C2PA producer coverage, version/runbook/security SSOT; legal scope, certificate provisioning, and real independent validation remain external gates.
4. **W5 acceptance harness:** no-provider matrix, exact L4 plan generator, and human/rights review record before any paid mutation.
5. **W5 live scenarios:** Fast, then S1, S2, S3, S4, S5; one fresh exact authorization per scenario, retry zero, finite provider/job caps, hard budget, pending-review-only artifacts, and explicit stop conditions.
6. **W5/W6 external closure:** publish, delivery, active-post metrics, production capacity, DR/alert drills, and owner signoff only under separate approvals.
7. **Deployment:** new code may reach production only after the user re-authorizes GitHub provenance or approves a separately designed equivalent immutable local provenance path. Never bypass the canonical wrapper with rsync or mutable source mounts.

## Batch A: W2-01-W2-04 lifecycle truth

### Task 1: Fail contradictory frontend lifecycle envelopes

**Files:**
- Modify: `web/src/lib/generationLifecycle.test.ts`
- Modify: `web/src/lib/generationLifecycle.ts`

**RED:** Add table cases proving that mixed envelopes such as `status=completed_full` with `completion_kind=bounded_media`, `full_media_success=false`, or `success=false` return `error`; unknown payloads without a legacy `success=true` signal must not default to `full`.

**GREEN:** Replace the current any-signal promotion with exact coherent envelopes:
- full requires `completed_full`, `full_media`, `request_succeeded=true`, `success=true`, and `full_media_success=true` when lifecycle fields are present;
- bounded requires coherent `completed_bounded` plus `no_media|bounded_media`, `request_succeeded=true`, `success=false`, and `full_media_success=false`;
- contradictions fail closed as `error`;
- legacy payloads are full only when they explicitly contain `success=true` and no lifecycle fields.

**Verify:** `cd web && npm test -- --run src/lib/generationLifecycle.test.ts`.

### Task 2: Persist and hydrate coherent full lifecycle truth

**Files:**
- Modify: `tests/test_scenario_state_persistence_schema_contract.py`
- Modify: `src/pipeline/state_manager.py`

**RED:** Add a coherent `completed_full/full_media` round-trip case and tamper cases for mixed status, false full flags, non-empty errors/degraded truth, and publish/delivery escalation.

**GREEN:** Generalize `_repository_payload()` and `_hydrate_execution_lifecycle()` to accept only two exact completed envelopes plus `policy_blocked`. `completed_full` must require `request_succeeded/success/full_media_success/pipeline_complete=true`, while `publish_allowed` and `delivery_accepted` remain false because generation completion is not acceptance or delivery authority. Preserve exact profile/cap equality checks.

**Verify:** `.venv/bin/python -m pytest -q tests/test_scenario_state_persistence_schema_contract.py`.

### Task 3: Derive scenario completion from required steps and artifacts

**Files:**
- Create: `src/pipeline/completion_truth.py`
- Create: `tests/test_scenario_completion_truth.py`
- Modify: `src/models/runtime_contracts.py`

**RED:** Parameterize S1-S5 fixtures for: all required evidence present; one required step missing; one required artifact empty; hard degraded; soft degraded; non-empty errors; stub/simulated media; and audit failure. Prove no partial or simulated fixture becomes full.

**GREEN:** Add a pure `derive_scenario_completion(state, expected_completion_kind)` function using `get_step_output()` and `SCENARIO_STEP_ORDERS`. For `full_media`, require every canonical step done and scenario artifacts from the design matrix:
- S1/S2: keyframes, clips, TTS, thumbnail, assembled video, passing audit;
- S3: source analysis/storyboard evidence, clips, audio, assembled video, passing audit;
- S4: uploaded-footage ownership/ref evidence, clips, TTS, thumbnail, assembled video, passing audit;
- S5: exactly six non-empty `config.product_sku.views` references, clips, TTS, assembled video,
  passing audit.
Any `pipeline_degraded`, `soft_degraded_reasons`, errors, stub, or `simulated=true` result must fail closed. Bounded/no-media retains `completed_bounded` and cannot set full/publish/delivery flags.

**Verify:** `.venv/bin/python -m pytest -q tests/test_scenario_completion_truth.py` and target Pyright/Ruff.

### Task 4: Use one terminal marker in StepRunner without enabling new authority

**Files:**
- Modify: `tests/test_generation_policy_step_guard.py`
- Modify: `src/pipeline/step_runner.py`
- Modify: `src/pipeline/generation_policy.py`

**RED:** Prove all terminal paths call the canonical derivation, bounded profiles remain bounded, and a synthetic server-owned full profile only completes when Task 3 evidence passes. Prove client config cannot select or tamper with full breadth.

**GREEN:** Replace duplicated `_mark_completed_bounded()` terminal calls with `_mark_execution_terminal()`. Extend the internal profile type to represent `full_media`, but keep current request-derived profiles bounded. Do not add a public request field or infer full breadth from `trusted_authorization_ref`. The later W5 L4 plan binder must be the only source of a persisted full profile.

**Verify:** `.venv/bin/python -m pytest -q tests/test_generation_policy_step_guard.py tests/test_scenario_completion_truth.py`.

### Task 5: Make scenario API and durable readback lifecycle-coherent

**Files:**
- Modify: `tests/test_scenario_step_regenerate_router.py`
- Modify: `tests/test_submit_idempotency_router.py`
- Modify: `src/routers/scenario.py`

**RED:** Add coherent full status/readback, contradictory snapshot, degraded terminal, and missing-envelope cases. `completed_full` must report progress 1.0; contradictory snapshots must fail closed instead of becoming completed.

**GREEN:** Centralize lifecycle projection for live state and durable snapshots. Recognize exact `completed_full`, preserve exact bounded truth, return `error` for degraded/failed, and return `invalid_state` or safe failure for malformed terminal envelopes.

**Verify:** focused pytest files above.

### Task 6: Align S1-S5 wrapper results with durable lifecycle truth

**Files:**
- Modify: `tests/test_s1_e2e.py`
- Modify: `tests/test_s2_e2e.py`
- Modify: `tests/test_s3_e2e.py`
- Modify: `tests/test_s4_e2e.py`
- Modify: `tests/test_s5_e2e.py`
- Modify: `src/pipeline/s1_product_pipeline.py`
- Modify: `src/pipeline/s2_brand_pipeline_v2.py`
- Modify: `src/pipeline/s3_remix_pipeline.py`
- Modify: `src/pipeline/s4_live_shoot_pipeline.py`
- Modify: `src/pipeline/s5_brand_vlog_pipeline.py`
- Create: `src/pipeline/media_truth.py`
- Modify: `src/pipeline/generation_policy.py`

**RED:** For each scenario, prove wrapper `success`, `_execution_completed`, lifecycle fields, artifacts, and degraded/error truth cannot disagree with the persisted state.

**GREEN:** Replace wrapper-local success inference with the canonical lifecycle projection. Preserve existing bounded response contracts and do not manufacture acceptance, publish, or delivery authority.

**Verify:** the five scenario E2E files plus generation-policy regressions.

### Task 7: Close generation fixture `simulated` truth

**Files:**
- Modify the canonical result contracts in `src/models/runtime_contracts.py`
- Audit/modify: `src/tools/seedance_client.py`
- Audit/modify: `src/skills/gpt_image_generate.py`
- Audit/modify: `src/skills/seedance_video_generate.py`
- Audit/modify: `src/skills/elevenlabs_tts.py`
- Audit/modify: `src/skills/remotion_assemble.py`
- Audit/modify: `src/services/fast_mode.py`
- Modify: `src/pipeline/s1_product_pipeline.py`
- Modify: `src/pipeline/s3_remix_pipeline.py`
- Modify: `src/pipeline/s4_live_shoot_pipeline.py`
- Modify: `src/pipeline/s5_brand_vlog_pipeline.py`
- Modify: `tests/test_media_clients.py`
- Modify: `tests/test_keyframe_images.py`
- Modify: `tests/test_provider_cost_poyo.py`
- Modify: `tests/test_provider_cost_tts.py`
- Modify: `tests/test_fast_mode_token_smoke_contract.py`
- Modify: `tests/test_runtime_contracts.py`
- Modify: `tests/test_s1_e2e.py`
- Modify: `tests/test_s2_e2e.py`
- Modify: `tests/test_s3_e2e.py`
- Modify: `tests/test_s4_e2e.py`
- Modify: `tests/test_s5_e2e.py`

**RED:** Prove stub/mock/fake transport outputs carry exact `simulated=true`, real fixture transport contracts carry exact `simulated=false`, and missing/non-boolean truth cannot enter `completed_full`.

**GREEN:** Project exact boolean simulation truth at provider adapter boundaries and preserve it through steps, scenario results, durable snapshots, and frontend types. Do not treat fixture naming or error text containing “simulated” as contract truth.

**Verify:** focused provider/skill tests, scenario completion truth, OpenAPI drift, frontend typecheck.

### Task 8: Close paid-step post-mutation error truth

**Files:**
- Extend the existing provider-cost fixture suites for LLM, GPT Image, Seedance, and CosyVoice
- Modify only provider adapters whose tests reveal an unclassified post-mutation outcome

**RED:** For every unrestricted full-media provider step, cover explicit rejection, ambiguous submit/poll, successful provider result followed by artifact failure, accounting failure, and restart readback. Assert no automatic retry and no full completion.

**GREEN:** Reuse the existing durable `released|ambiguous|accounting_error|provider_cost_artifact_failed` states; only add missing projection/propagation. Never turn an ambiguous paid outcome into a free retry.

**Verify:** provider-cost regression, scenario completion truth, restart tests, secret/log scans.

### Task 9: Unify degraded/pending-review recovery UI

**Files:**
- Audit/modify: `web/src/components/StageProgress.tsx`
- Audit/modify: `web/src/components/OneShotResultView.tsx`
- Audit/modify: `web/src/components/FastModePanel.tsx`
- Audit/modify: `web/src/components/PipelineStatusBar.tsx`
- Audit/modify: `web/src/components/StepByStepView.tsx`
- Audit/modify: `web/src/components/VideoWorkflow.tsx`
- Audit/modify: `web/src/app/page.tsx`
- Modify: `web/src/components/StageProgress.test.tsx`
- Modify: `web/src/components/OneShotResultView.test.tsx`
- Modify: `web/src/components/FastModePanel.test.tsx`
- Modify: `web/src/components/PipelineStatusBar.test.tsx`
- Modify: `web/src/components/StepByStepView.test.tsx`
- Modify: `web/src/app/__tests__/page-smoke.test.ts`

**RED:** Prove degraded, pending-review full, bounded, and error states render distinct labels/actions; recovery never auto-resubmits; publish/delivery actions stay unavailable before acceptance.

**GREEN:** Consume canonical backend lifecycle only, expose readback/retry-from-safe-boundary actions, preserve the idempotency key for ambiguity, and require explicit user action for a new authorized submit.

**Verify:** focused Vitest, frontend lint/typecheck/OpenAPI/build, then browser fixture acceptance.

**Local result (2026-07-22):** implementation and automated gates are green (`68 files / 399
tests`, lint, TypeScript, OpenAPI, and 32-route build). Browser fixture acceptance is explicitly
blocked before navigation because bundled Chromium is absent and system Chrome startup hangs; no
application assertion ran, so this is neither browser PASS nor application FAIL.

### Task 10: Batch A integration and independent review loop

**Files:**
- Update: `docs/workflows/enterprise-ai-content-all-scenarios-roadmap-20260711.md`
- Update: relevant runbooks/API reference only where behavior changed
- Update: `.kiro/plan/task_plan.md`, `.kiro/plan/progress.md`, `.kiro/plan/findings.md`

Run focused backend/frontend suites, affected regression, full backend/frontend gates, OpenAPI drift, lint, typecheck, build, secret/log scans, and local/disposable persistence checks. Then start an independent read-only review thread covering requirement completeness, logic correctness, edge cases, code quality, test coverage, and actual run results. Return a fix list to the main thread, fix accepted findings, and have the same reviewer re-verify until `PASS / APPROVE` or a concrete blocker is recorded.

**Post-fix evidence (2026-07-22):** review pass 1 found four accepted issues in final-artifact
truth, profile/lifecycle binding, S4 ownership/rights evidence, and frontend terminal projection.
All received RED/GREEN fixes. Fresh backend is `4035 passed, 9 skipped, 16 deselected`; canonical
S1-S5 hermetic is `282 passed`; frontend is `68 files / 400 tests`; lint, TypeScript, OpenAPI,
32-route build, core Pyright, full Ruff, diff check, and current-diff secret scan are green. The
same reviewer re-verification remains required before Batch A completion.

## Later batches

After Batch A passes independent review, create one exact executable TDD plan per contiguous roadmap batch before changing code:

- Batch B: W2-05-W2-09 PostgreSQL fail-fast/readiness/bootstrap/PG18.
- Batch C: W2-10-W2-13 state parity, bounded rewind, request-scoped keys.
- Batch D: W2-14-W2-17 frontend completion/Gate/S5 six-input/accessibility.
- Batch E: W3 local reproducibility, type, observability, backup manifest/recovery.
- Batch F: W4 local transparency/C2PA/version/docs/security SSOT.
- Batch G: W5-01-W5-03 no-provider harness, L4 plan generator, human/rights records.
- Batch H: six separately authorized live scenario packets.
- Batch I: separately authorized publish/delivery/metrics/capacity/DR/owner acceptance.

Each batch must update the acceptance matrix with evidence grade, exact commands, exact SHA, external side effects, remaining blockers, rollback path, and independent review result.
