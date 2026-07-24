---
title: "W5 Fast One-Shot Operator Governance Plan"
doc_type: workflow
module: acceptance
topic: fast-one-shot-operator
status: active
created: 2026-07-24
updated: 2026-07-24
owner: self
source: human+ai
---

# W5 Fast One-Shot Operator Governance Plan

> This batch is local/provider-off `L2-fixture-or-dry-run` evidence only. It
> does not authorize a provider request, production mutation, GitHub update,
> publish, delivery, or reuse of consumed W5 authority.

## Goal

Replace the ignored incident-only W5 helper with one tracked, testable operator
path that preserves exact backend routes, consumes one marker before one POST,
never retries, records only bounded secret-free evidence, supports poll-only
recovery, and deterministically returns the production backend to its exact
provider-off configuration after any future separately authorized window.

## Task 1 — RED contracts

- Freeze canonical `/fast/submit` and `/fast/status/{task_id}` OpenAPI methods.
- Prove OpenAPI unavailability, malformed JSON, missing methods, and proxy-only
  paths fail before marker creation.
- Prove O_EXCL marker creation precedes the only POST and an existing marker
  prevents all HTTP mutation.
- Prove HTTP rejection and transport ambiguity are distinct, bounded, and
  never retried.
- Prove poll recovery performs GET only, terminates finitely, and stores only a
  safe projection.
- Prove evidence files are regular, create-only, `0600`, bounded, and cannot
  leak a raw key, API key, prompt, DSN, response body, exception, or absolute
  path.
- Prove provider-off restoration runs for success, rejection, ambiguity,
  blocked input, and unexpected failure; restore failure is never hidden.

## Task 2 — Tracked core and thin CLI

- Add a dependency-injected core under `src/operations/`.
- Reuse canonical W5 plan/activation/runtime loader validation; do not create a
  second authorization model.
- Add a thin `scripts/w5_fast_one_shot_operator.py` command with dotenv
  disabled, transient raw key on stdin, a separate exact execute environment
  gate, fixed loopback backend, finite timeouts/polls, and stable JSON exits.
- Import HTTP/database dependencies lazily and catch only transport ambiguity;
  programming/configuration errors remain blocked rather than misclassified.

## Task 3 — Provider-off lifecycle

- Add a repository-owned Lighthouse window wrapper that pins the reviewed
  release plus backend revision and immutable image ID, snapshots the exact
  environment, installs an EXIT/signal trap before mutation, uses the fixed
  `/run/ai-video-w5` private leaf, and recreates only backend.
- On every exit, capture only safe evidence, restore the byte-identical original
  environment, recreate the exact backend image, and verify readiness/image and
  W5-path removal. Safe marker/outcomes live in an activation-scoped `0700`
  directory on the persistent output volume and survive recreate; both its
  parent and activation leaf are owned by the resolved backend UID/GID so the
  default non-root user can traverse it while unrelated UIDs cannot. Private
  input files disappear with the recreated container. Host-stage retention/
  deletion remains caller-owned and is never performed by a broad cleanup
  command.
- No success path may disable the restore trap. A restore failure overrides any
  apparent operation success and remains an explicit blocker.

## Task 4 — Documentation and verification

- Add the operator runbook with preflight, evidence, failure classification,
  provider-off restore, and fresh-authorization gates.
- Run focused tests, shell syntax, Ruff, source Pyright, affected regression,
  full `make ci`, docs/frontmatter, diff, and bounded secret scans.

## Task 5 — Independent review loop

Start one independent read-only reviewer after main-thread verification. Require
findings across requirements completeness, logic correctness, edge cases, code
quality, test coverage, and actual runtime results. Main thread owns all fixes;
the same reviewer repeats until `PASS / APPROVE` with zero accepted actionable
findings or records an exact blocker.

## External gate

After local approval, GitHub/CI, provider-off deployment/L3, and a fresh W5-04
activation/submit authorization remain three separate approvals. The historical
marker, activation, binding, and raw idempotency key are permanently unusable.
