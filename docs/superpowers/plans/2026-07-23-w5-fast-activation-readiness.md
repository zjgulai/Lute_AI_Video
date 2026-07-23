# W5 Fast Activation Readiness Implementation Plan

> **For Codex:** Execute this plan in strict RED -> GREEN -> focused
> regression -> full local gate -> independent six-dimension review cycles.
> This batch is provider-off L2 evidence only.

**Goal:** Add the missing local prerequisite for W5-04: a strict private
activation-record parser and Fast readiness projection that bind one approved
activation to one canonical W5 Fast draft without authorizing or executing a
provider call.

**Architecture:** Add one dependency-free domain module beside the W5
acceptance harness. It reloads the original bounded JSON for both the draft and
activation, rejects duplicate/non-finite/unknown input, validates exact
tenant/scenario/sample/plan/budget/job-cap/time bindings, and returns an
immutable readiness report. Add a read-only CLI for operators. Do not change
Fast routes, request models, generation-policy resolution, provider-cost
accounts, provider clients, persistence, production, publish, or delivery.

**Evidence ceiling:** L2 local/static/fixture. A passing readiness report is not
an L4 authorization, provider call permission, consumed one-shot marker,
runtime execution profile, provider-cost account, artifact, human acceptance,
publish, or delivery evidence.

## Safety invariants

- Activation scope is exactly `w5-fast-activation.v1` and scenario is exactly
  `fast`.
- The activation binds the deterministic W5 plan ID plus exact tenant, sample,
  budget nanos, selected optional media, and provider job caps.
- `single_submit=true`, `automatic_retry_cap=0`,
  `provider_max_retries=0`, and `artifact_disposition=pending_review` are
  literals.
- `publish_allowed=false` and `delivery_accepted=false` remain literals.
- Approval time must be UTC, not future, and inside the plan's half-open
  validity window; activation expiry must also remain within the plan window.
- Original JSON is bounded and duplicate keys, floats, non-finite values,
  unknown fields, unsafe identifiers, and path-like refs fail closed.
- Activation files are accepted only under repository `tmp/` or outside the
  repository; tracked/formal paths cannot become private authority.
- Readiness output always keeps `provider_call_allowed=false` and
  `execution_authorized=false`.
- No environment/key lookup, network/provider import, database/store access,
  HTTP mutation, output write, approve transition, or execute transition.

## Task 1: Strict Fast activation record

**Files:**

- Create: `src/pipeline/w5_fast_activation.py`
- Create: `tests/test_w5_fast_activation.py`

**RED:** Prove exact valid binding and rejection of wrong plan, tenant, sample,
scenario, budget, cap, optional-media choice, retry, disposition, authority
flags, future/expired/out-of-plan time, duplicate JSON keys, floats,
non-finite values, unsafe identifiers, oversized input, and non-private paths.

**GREEN:** Add strict frozen models and bounded original-JSON loaders. Reuse
`validate_w5_plan_draft_json` for the draft; do not duplicate the W5 contract
or plan digest logic.

## Task 2: Provider-off readiness projection

**Files:**

- Modify: `src/pipeline/w5_fast_activation.py`
- Modify: `tests/test_w5_fast_activation.py`

**RED:** Prove missing/invalid plan or activation returns stable block checks;
an exact fixture can become `ready_for_private_binding=true` while
`provider_call_allowed=false` and `execution_authorized=false`; reports contain
no prompt, credential, host path, or provider response.

**GREEN:** Add one immutable report with bounded check names/details and the
exact safe plan/activation identifiers. Do not derive an existing
single-provider budget authorization or touch provider-cost persistence in this
batch.

## Task 3: Read-only CLI and governance

**Files:**

- Create: `scripts/check_w5_fast_readiness.py`
- Create: `tests/test_check_w5_fast_readiness.py`
- Modify: `configs/scripts-governance-contract.json`
- Modify: `docs/runbooks/scripts-governance.md`
- Modify: `tests/test_scripts_governance.py` only if the existing inventory
  contract requires a test extension.

**RED:** Prove the CLI requires explicit plan and activation paths, prints JSON
only, never writes, returns stable exit `2` when blocked/bad, succeeds only for
the exact fixture, and has no environment/network/provider/database/execute
surface.

**GREEN:** Add a minimal argparse wrapper over the domain report.

## Task 4: Verification and independent review loop

**Main-thread verification:**

```bash
env -u API_KEY -u TEST_BUNDLE_KEY uv run --frozen --no-sync pytest -q \
  tests/test_w5_fast_activation.py \
  tests/test_check_w5_fast_readiness.py \
  tests/test_w5_acceptance_harness.py \
  tests/test_build_w5_acceptance_plan.py \
  tests/test_scripts_governance.py
uv run --frozen --no-sync ruff check \
  src/pipeline/w5_fast_activation.py \
  scripts/check_w5_fast_readiness.py \
  tests/test_w5_fast_activation.py \
  tests/test_check_w5_fast_readiness.py
uv run --frozen --no-sync pyright \
  src/pipeline/w5_fast_activation.py
make ci
git diff --check
```

Run a bounded strong-secret scan and confirm the Git index remains empty.

**Independent review:** Reuse the same read-only reviewer. Require explicit
findings across requirements completeness, logic correctness, edge cases, code
quality, test coverage, and actual runtime results. The reviewer must not edit.

**Repair loop:** Main thread adds RED tests and fixes every accepted finding,
then sends the exact change set to the same reviewer. Repeat until
`PASS / APPROVE` with `accepted_actionable_findings=0`, or report the exact
blocker.

## Task 5: Close only the prerequisite

Update the roadmap/project guide/plan only after independent approval. Record
this batch as `W5-04 readiness completed_local`, while W5-04 live Fast
submission remains `blocked_external`. Do not mark W5-04 itself complete.
