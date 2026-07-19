---
title: W1-25 Publish Receipt and Protocol Calibration Implementation Plan
doc_type: workflow
module: distribution
topic: publish-receipt-protocol-calibration
status: stable
created: 2026-07-14
updated: 2026-07-20
owner: self
source: human+ai
---

# W1-25 Publish Receipt and Protocol Calibration Implementation Plan

> **Execution rule:** Implement this plan task-by-task in the main thread. The
> user explicitly prohibited subagents. Checkboxes are updated only after fresh
> evidence passes.

**Goal:** Calibrate TikTok and Shopify publishing to the current official
protocols, move all preflight observations before acceptance consumption, and
make every new `published` attempt carry a strict durable receipt without
performing any real provider call.

**Approved specification:**
`docs/superpowers/specs/2026-07-14-publish-receipt-protocol-calibration-design.md`
with `status: stable`.

**Architecture:** Keep W1-23's tenant-bound single-use acceptance ledger and
W1-24's fail-closed connector truth. Add strict request options and receipt
models, a read-only internal acceptance inspection, typed connector preflight,
and a retained connector instance for the sequence `preflight -> consume ->
publish`. Persist receipt, status, post projection, and stable error in one CAS.
TikTok uses Content Posting API v2 Direct Post with FILE_UPLOAD. Shopify uses
Admin GraphQL 2026-07 staged VIDEO upload, file readiness, exact Product GID
association, and association readback. Legacy status becomes receipt-only and
performs no external call.

**Tech stack:** Python 3.11+, FastAPI, Pydantic v2, httpx, asyncpg, SQLite,
Alembic, pytest/pytest-asyncio, Ruff, PostgreSQL 18 disposable tests, Next.js 16,
React 19, TypeScript, Vitest, ESLint.

## Global constraints

- Preserve all existing Wave 1 dirty-worktree changes. Never reset, restore,
  reformat, delete, or overwrite unrelated files.
- Do not use subagents. Main-thread self-review is not independent review.
- Do not read `.env`, `.env.prod`, private keys, or credential files. Fixture
  credentials are explicit test-only strings supplied through `monkeypatch`.
- No real HTTP/provider/status call, SSH, deploy, production migration, live
  publish, delivery, metrics pull, stage, commit, push, PR, or merge.
- Provider flags default off. Tests must block construction of an un-injected
  network client and block socket escapes.
- Preserve one acceptance, one attempt, one connector `publish` invocation,
  no mutation retry, no authority restore, and no automatic reconciliation.
- TikTok chunk PUTs are sequential parts of one initialized upload task, not
  retries. Bounded polling observes the same operation/resource only.
- Stable errors and logs contain no credential, upload/staged URL, signed
  parameter, raw provider payload/error, local absolute path, product text, or
  creator PII.
- Every behavior change follows RED -> named expected failure -> minimal GREEN
  -> focused regression -> Ruff/diff check.
- If the same path fails a third verification, stop patching and re-audit the
  protocol/state boundary before continuing.
- Fixed evidence ceiling:
  `implementation_complete_local / independent_review_pending`,
  `independent_review=false`, `production unchanged`, `provider_call=false`,
  `provider_attempt_made=false`, `real_connector_call=false`,
  `external_status_call=false`, `live_publish=false`, `live_send=false`,
  `database_write=local-test-only`.

## File structure

### Create

- `tests/test_publish_request_options.py`
- `tests/test_publish_receipt_contracts.py`
- `tests/test_publish_preflight.py`
- `tests/test_tiktok_direct_post_protocol.py`
- `tests/test_shopify_media_protocol.py`
- `tests/test_publish_attempt_readback.py`
- `migrations/alembic/versions/a6b7c8d9e0f1_add_publish_receipt.py`
- `docs/runbooks/publish-receipt-protocol-calibration.md`
- `docs/workflows/enterprise-ai-content-all-scenarios-roadmap-20260711.md`

### Modify

- `src/config.py`
- `src/connectors/base.py`
- `src/connectors/registry.py`
- `src/connectors/tiktok_connector.py`
- `src/connectors/shopify_connector.py`
- `src/connectors/publish_engine.py`
- `src/models/publish_attempt.py`
- `src/services/artifact_acceptance.py`
- `src/services/publish_attempt.py`
- `src/storage/publish_attempt_repository.py`
- `src/storage/db.py`
- `src/storage/migrations/001_init.sql`
- `src/routers/distribution.py`
- `.env.example`
- active workflow/hermetic/no-provider contracts that still name legacy envs
- existing W1-22/W1-23/W1-24 publish and connector tests
- `web/src/components/api.ts`
- `web/src/types/api.generated.ts` through the existing generator only
- current runbook/reference/roadmap/Kiro/SDD state documents after fresh proof

### Explicitly do not modify

- acceptance HTTP consume/inspect authority or acceptance UI
- publish/review product UI
- generation provider clients
- production secret/deploy environment files
- delivery, active-post metrics, C2PA, W1-26 live harness behavior
- archive/research historical bodies

---

## Task 0: Approved spec and baseline

- [x] Update the approved specification to `status: stable` after the user's
  explicit review.
- [x] Record scoped `git status`, Alembic head, current focused pass baseline,
  and exact legacy env references without reading values.
- [x] Confirm the new migration revision does not collide and the current head
  is `f9a2b3c4d5e6`.

## Task 1: Strict request options and canonical configuration

**RED files:** `tests/test_publish_request_options.py`, focused existing router,
service, connector-readiness, OpenAPI, workflow, and no-provider tests.

- [x] Add strict discriminated `TikTokPublishOptions` and
  `ShopifyPublishOptions`; require `platform_options` and exact top-level
  platform match.
- [x] Reject bool coercion, unknown fields, missing commercial consent, invalid
  privacy, and non-positive/non-Product Shopify GIDs.
- [x] Add `TIKTOK_PUBLISH_ENABLED` and `SHOPIFY_PUBLISH_ENABLED`; only explicit
  truthy values enable publishing and unset/blank/unknown values remain off.
- [x] Make `SHOPIFY_ACCESS_TOKEN` the sole active runtime token. Any non-empty
  legacy token/endpoint/username override makes readiness fail closed with
  `invalid_configuration` without exposing the value.
- [x] Restrict `SHOPIFY_STORE_URL` to one lowercase
  `<shop>.myshopify.com` host and pin the endpoint to Admin GraphQL `2026-07`.
- [x] Fix TikTok publish endpoints to `https://open.tiktokapis.com`; retain the
  separate official metrics query path without an override fallback.
- [x] Run request/config RED, implement minimal GREEN, then focused Ruff and
  diff checks.

## Task 2: Receipt and connector preflight vocabulary

**RED files:** `tests/test_publish_receipt_contracts.py`,
`tests/test_publish_preflight.py`.

- [x] Add strict `PublishReceiptV1` with canonical UTF-8 JSON <= 8 KiB,
  platform-specific status/ID/URL invariants, exact `simulated=false`, and safe
  partial-receipt validation.
- [x] Add `preflight_failed` and stable preflight error codes to models and
  repository vocabularies.
- [x] Add typed `ConnectorPreflightRejected`,
  `ConnectorPreflightUnavailable`, and immutable TikTok/Shopify snapshot
  contracts containing safe facts only.
- [x] Extend ambiguous connector outcomes to carry an optional safe partial
  receipt mapping without raw provider material.
- [x] Make the registry return one retained connector instance for service
  preflight and publish; compatibility engine explicitly performs preflight
  before publish.
- [x] Confirm receipt models reject mock markers, wrong provider statuses,
  operation/resource confusion, unsafe TikTok URLs, Shopify post projections,
  raw payload extras, and oversized UTF-8 JSON.

## Task 3: Internal acceptance inspection and pre-consume orchestration

**RED files:** `tests/test_artifact_acceptance_service.py`,
`tests/test_publish_preflight.py`, `tests/test_publish_attempt_service.py`.

- [x] Add internal-only `inspect_for_publish` to validate tenant, decision,
  availability, expiry, exact artifact path/hash/size, and source authority
  without changing acceptance state or creating consume evidence.
- [x] Change service order to readiness -> prepared -> inspect artifact ->
  connector preflight -> consume -> durable acceptance_consumed -> revalidate
  artifact -> exactly one connector publish -> terminal CAS.
- [x] Persist deterministic and unavailable preflight outcomes as
  `prepared -> preflight_failed`, with no receipt/post projection, no consume,
  and `retry_allowed=true`.
- [x] Preserve existing authorization-failure and uncertain-consume behavior;
  preflight success does not weaken the second consume-time artifact check.
- [x] Ensure preflight and publish use the same platform/options and retained
  snapshot; connector mutation is never called after a failed preflight.
- [x] Run ordering, concurrency, tenant, expiry, byte-drift, and no-network
  focused regression.

## Task 4: Receipt schema, repository CAS, and readback primitives

**RED files:** `tests/test_publish_attempt_repository.py`,
`tests/test_publish_attempt_pg18.py`, `tests/test_publish_attempt_readback.py`,
backup/restore/readiness tests.

- [x] Add nullable `publish_logs.receipt` (`JSONB` in PostgreSQL, canonical
  `TEXT` in SQLite) in Alembic, fresh-init SQL, fresh SQLite, compat backfill,
  and required-column contracts.
- [x] Add the non-unique tenant/platform/post partial index limited to trusted
  published rows with non-null receipt/post ID.
- [x] Extend repository decode/encode with strict receipt validation and fail
  closed on malformed persisted receipts.
- [x] Make terminal CAS write status, receipt, post projection, stable error,
  and updated timestamp atomically. New `published` requires a valid published
  receipt; preflight/failed/ambiguous projections remain constrained.
- [x] Keep historical `published + receipt=null` readable only as
  legacy/unverified and never eligible for status authority.
- [x] Add tenant-bound attempt readback and exact published-receipt lookup;
  duplicate contradictory receipt matches fail closed rather than selecting the
  newest row.
- [x] Prove upgrade/downgrade/re-upgrade and fresh/compat behavior on SQLite and
  disposable PostgreSQL 18.

## Task 5: TikTok Content Posting API v2 protocol

**RED file:** `tests/test_tiktok_direct_post_protocol.py`, plus existing
connector truth/log/engine tests.

- [x] Validate accepted MP4/MOV/WebM artifact bytes, MIME, size, finite media
  duration, title constraints, and official chunk-plan limits using injected
  probes and small fixtures.
- [x] Preflight with creator info; enforce returned privacy options,
  interaction restrictions, maximum duration, and explicit commercial toggles.
- [x] Initialize Direct Post exactly once with `source=FILE_UPLOAD`, approved
  post info, and server-forced `is_aigc=true`.
- [x] Strictly validate `publish_id` and HTTPS upload URL; upload ordered chunks
  once each with exact Content-Range/Content-Length and no redirect.
- [x] Poll the same publish ID within fixed count and monotonic deadline; accept
  only protocol-appropriate statuses.
- [x] Treat `FAILED` as deterministic post-consume failure; timeout, unknown
  status, parse/shape drift, transport uncertainty, or conflicting public IDs as
  ambiguous with only a safe partial receipt.
- [x] Create published receipt only at `PUBLISH_COMPLETE`; never treat
  `publish_id` as post ID and never derive a username URL.
- [x] Optionally query exact video ID for share URL; validate HTTPS,
  TikTok host, no port/query/fragment/userinfo, exact
  `/@creator/video/<post_id>` path, and matching ID.
- [x] Run protocol ordering/no-retry/no-network/log-safety regression.

## Task 6: Shopify Admin GraphQL 2026-07 video protocol

**RED file:** `tests/test_shopify_media_protocol.py`, plus existing connector
truth/log/engine tests.

- [x] Validate exact Product GID, accepted video MIME/size/duration, canonical
  store host, flag, and token.
- [x] Preflight exact product identity and current app scopes
  (`read_products`, `write_products`, `write_files`) with read-only GraphQL.
- [x] Execute `stagedUploadsCreate` once with `resource: VIDEO` and `fileSize`;
  validate the staged HTTPS target/parameters and deny redirects/private or
  unsafe targets.
- [x] Upload multipart once without Shopify credential, then run `fileCreate`
  once and require an exact Video GID.
- [x] Poll only that Video GID to `READY`; treat `FAILED` as deterministic and
  uncertainty/timeouts as ambiguous.
- [x] Run `fileUpdate(referencesToAdd: [exact Product GID])` once and require
  exact product-media readback containing the same Video GID.
- [x] Return receipt scope `shopify_product_media` with Video/Product GIDs,
  `READY`, no post ID/URL, and no public-visibility claim.
- [x] Remove product-name search, Admin URL projection, Video-GID-as-post, and
  any legacy token/endpoint fallback.
- [x] Run exact query/variables/order/no-retry/no-token-upload/log-safety tests.

## Task 7: HTTP readback, legacy status hardening, and frontend types

**RED files:** `tests/test_publish_attempt_readback.py`, existing route/auth and
OpenAPI drift tests, frontend API tests.

- [x] Add `GET /distribution/publish-attempts/{attempt_id}` with
  `artifact:publish|all`, tenant-bound 404 behavior, safe projection, no external
  call, and stable 503 on store failure.
- [x] Include safe receipt in publish success response and preserve strict
  success/consume/no-retry literals.
- [x] Deprecate legacy status as durable TikTok receipt readback only; Shopify
  returns stable 410, missing exact receipt returns 404, contradictory duplicate
  receipts return 503, and no path calls a connector or writes the database.
- [x] Require publish permission for status; public post ID is never passed as
  TikTok publish operation ID.
- [x] Add frontend canonical attempt helper/type without new UI and regenerate
  OpenAPI TypeScript through the existing command.
- [x] Run auth-before-parse, cross-tenant, safe-error, OpenAPI/typegen/drift,
  Vitest, ESLint, typecheck, and build focused gates.

## Task 8: Active configuration and documentation migration

- [x] Update `.env.example`, active workflows, hermetic/no-provider contracts,
  config tests, and current runbooks/references to canonical variable names and
  default-off flags.
- [x] Do not rewrite archive/research history; current docs may mark superseded
  names without claiming historical use.
- [x] Add the W1-25 runbook with failure matrix, receipt semantics, no-retry
  rule, local rollback, future deployment ordering, and exact W1-26 authorization
  gate.
- [x] Run secret-name drift, frontmatter, docs-link, archive-drift, and sensitive
  pattern checks.

## Task 9: Mandatory regression and disposable PostgreSQL 18

- [x] Run all new W1-25 tests and focused W1-22/W1-23/W1-24 suites.
- [x] Run disposable PostgreSQL 18 migration/repository/service/readback tests.
- [x] Run backup/restore, schema readiness, auth, OpenAPI, metrics compatibility,
  and hermetic socket/client-construction guards.
- [x] Run backend Ruff and `make ci`; record fresh exact outputs only.
- [x] Run frontend Vitest, ESLint, TypeScript, OpenAPI drift, and Next build.
- [x] Run `git diff --check`, conflict/TODO/placeholder/mock-ID, secret pattern,
  and temporary artifact scans over the W1-25 manifest.

## Task 10: Evidence, state synchronization, and two-pass self-review

- [x] Update the tracked roadmap and protocol-calibration runbook from fresh evidence, including
  RED diagnostics, commands, pass/fail counts, file manifest, evidence ceiling,
  and exact unverified W1-26 work.
- [x] Synchronize roadmap, AGENTS project status, runbook index, API reference,
  `AGENTS.md` without upgrading evidence
  beyond what was actually run.
- [x] Self-review pass 1: protocol, state machine, transaction, auth, privacy,
  SSRF, secret, retry, and migration correctness.
- [x] Self-review pass 2: tests, generated files, docs, diff scope, historical
  compatibility, and claim/evidence alignment.
- [x] Final state remains
  `implementation_complete_local / independent_review_pending` with
  `independent_review=false`; no independent-review claim is permitted.
