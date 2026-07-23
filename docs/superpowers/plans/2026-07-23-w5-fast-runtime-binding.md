---
title: "W5 Fast Runtime Binding Implementation Plan"
doc_type: workflow
module: acceptance
topic: fast-runtime-binding
status: stable
created: 2026-07-23
updated: 2026-07-23
owner: self
source: human+ai
---

# W5 Fast Runtime Binding Implementation Plan

> Execute strict RED -> GREEN -> focused regression -> full local gate ->
> independent six-dimension review. Provider calls, production deployment,
> publish, and delivery stay off throughout this plan.

## Goal

Close the local runtime prerequisite for W5-04 by binding one private Fast
activation to one exact request/idempotency key, consuming it atomically with
the durable submission claim, and injecting its total cap into provider-cost
account creation.

## Task 1 — Runtime binding domain and builder

Create `src/pipeline/w5_fast_runtime.py`, a private builder CLI, and tests.
Reject duplicate/non-finite/oversized JSON, unsafe/private paths, mismatched
plan/activation/request/key/model/policy, any mutation of the complete
canonical activation content, partial environment configuration,
future/expired authority, floating request numbers, and all prompt/key
leakage.

## Task 2 — Provider-neutral plan budget

Add a strict validated plan-budget authority to
`src/services/provider_cost.py`. Update provider execution initialization to
accept either reviewed authority shape while preserving all existing
single-provider behavior. Prove server-cap minimum, expiry, source identity,
and type rejection.

## Task 3 — Durable activation consumption

Add `trusted_authorization_ref` to the SQLite/PostgreSQL schema, Alembic
migration, repository claim, backup/restore contract, and tests. Enforce one
activation per tenant with a partial unique index. Distinguish same-key replay,
payload conflict, store failure, and already-consumed activation without
releasing authority.

## Task 4 — Fast route binding

When all private W5 paths are absent, preserve current behavior. When W5 mode is
configured, require an exact binding before a new owner claim, persist the
activation ID in the claim, pass the validated plan budget to provider
execution initialization, keep retry zero/pending review, and expose no new
client authority field. Existing same-key replay must stay read-only even after
activation expiry, private-packet removal, or packet rotation. Resolve exact
durable replay before loading the current private packet; only a new owner may
consume current authority. Compare the complete server-owned LLM and video
provider/model/runtime envelope before the durable claim.

## Task 5 — Verification

Run focused domain/service/repository/router tests with provider keys removed,
SQLite restart/parity, disposable PostgreSQL 18 migration and concurrency,
Fast generation-policy/idempotency/provider-cost regressions, Ruff, source
Pyright, full `make ci`, diff, secret, and empty-index gates.

## Task 6 — Independent review loop

Send the exact implementation and fresh runtime results to the same independent
read-only reviewer. Require findings across requirements completeness, logic
correctness, edge cases, code quality, test coverage, and actual runtime
results. Main thread owns fixes; the same reviewer repeats until
`PASS / APPROVE` with zero accepted findings or an exact blocker is recorded.

## Task 7 — External gate

Only after local approval, build a fresh plan/activation/runtime-binding packet
with a maximum four-hour plan and two-hour activation window. Re-run provider
and account readiness. Production deploy and exactly one Fast submit require
the final packet confirmation and remain separate from this provider-off plan.
