---
title: Publish Receipt and Protocol Calibration
doc_type: workflow
module: backend-frontend
topic: publish-receipt-protocol-calibration
status: stable
created: 2026-07-14
updated: 2026-07-14
owner: self
source: human+ai
---

# Publish Receipt and Protocol Calibration

## Scope and trigger

Use this runbook when an acceptance-backed TikTok or Shopify publish attempt is
rejected before consume, fails or becomes ambiguous after consume, returns a
receipt that cannot be trusted, or cannot be read back from the durable attempt
ledger. It covers W1-25 local protocol, receipt, configuration, and recovery
semantics.

It does not authorize credential access, a real provider/status call,
production migration or deployment, live publish, delivery, deletion,
reconciliation, or acceptance restoration. Those actions remain outside this
runbook. The current evidence boundary is `completed_local`,
`independent_review=true`, L2 local/fixture/fake-transport/disposable-PG18/build
only, and `production unchanged`.

Expected diagnosis time is 2-10 minutes for pre-consume failures and 10-30
minutes for post-consume ambiguity.

## Related contracts and code

- Approved design record:
  `docs/superpowers/specs/2026-07-14-publish-receipt-protocol-calibration-design.md`
- Implementation record:
  `docs/superpowers/plans/2026-07-14-publish-receipt-protocol-calibration.md`
- [W1-23 acceptance consumption](./publish-acceptance-consumption.md)
- [W1-24 connector truth](./publish-connector-truth.md)
- `src/models/publish_attempt.py`
- `src/services/publish_attempt.py`
- `src/storage/publish_attempt_repository.py`
- `src/connectors/tiktok_connector.py`
- `src/connectors/shopify_connector.py`
- `src/routers/distribution.py`

## Canonical active configuration

Publishing is disabled unless its flag is explicitly truthy. The only active
publish variables are:

- `TIKTOK_PUBLISH_ENABLED`
- `TIKTOK_ACCESS_TOKEN`
- `SHOPIFY_PUBLISH_ENABLED`
- `SHOPIFY_ACCESS_TOKEN`
- `SHOPIFY_STORE_URL`, as one lowercase `<shop>.myshopify.com` host

TikTok publish endpoints are fixed under `https://open.tiktokapis.com`.
Shopify Admin GraphQL is fixed at `2026-07`. Do not configure endpoint or URL
templates.

The following legacy or override variables are not fallbacks. Any non-empty
value makes publish readiness fail closed with `invalid_configuration`:

- `TIKTOK_USERNAME`
- `TIKTOK_API_UPLOAD_URL`
- `TIKTOK_API_BASE_URL`
- `SHOPIFY_API_KEY`
- `SHOPIFY_ADMIN_TOKEN`
- `SHOPIFY_API_PASSWORD`
- `SHOPIFY_GRAPHQL_URL_TEMPLATE`

Do not print variable values while diagnosing configuration. Confirm names and
presence only through an approved secret-management path.

## Failure matrix

| Observation | HTTP | Attempt state | Stable code | Acceptance | Next action |
|---|---:|---|---|---|---|
| Request or platform options invalid | 422 | none | safe validation detail | unconsumed | Correct the request. |
| Flag off, credential missing, or configuration invalid | 503 | none | `publish_connector_not_ready` | unconsumed | Repair configuration, then submit a new request. |
| Acceptance unavailable or artifact mismatch | 404/409/503 | `authorization_failed` or unknown | existing acceptance code | unconsumed or unknown | Follow the W1-23 acceptance runbook. |
| Deterministic read-only preflight rejection | 409 | `preflight_failed` | `publish_preflight_rejected` | unconsumed | Correct options, product, scopes, or media. |
| Read-only preflight timeout, 5xx, parse, or shape uncertainty | 502 | `preflight_failed` | `publish_preflight_unavailable` | unconsumed | A later explicit request may preflight again. |
| Configuration disappears after consume but before mutation | 502 | `failed` | `publish_connector_not_ready_after_consume` | consumed | Do not retry or restore authority. |
| Provider returns an explicit failure after mutation | 502 | `failed` | `publish_connector_failed` | consumed | Reconcile manually before any new review. |
| Mutation, polling, response shape, or terminal truth is uncertain | 502 | `ambiguous` | `publish_outcome_ambiguous` | consumed | Freeze automation and reconcile manually. |
| Receipt is missing, malformed, mock-marked, or contradictory | 502 | `ambiguous` | `publish_outcome_ambiguous` | consumed | Treat as unknown external outcome. |
| Terminal CAS cannot be proven | 500 | unknown | `publish_attempt_state_unknown` | consumed | Inspect durable state; do not repeat mutation. |
| Strict terminal receipt persisted | 200 | `published` | none | consumed | Read back the attempt; do not reuse acceptance. |

`retry_allowed=true` only means the failed attempt proved that acceptance was
not consumed. It is not authority to reuse an old request without passing all
checks again.

## Receipt semantics

Every newly written `published` attempt must contain one strict
`publish-receipt.v1` document and an exact legacy post projection derived from
that receipt. Receipt JSON is canonical, limited to 8 KiB, and cannot contain
credentials, signed upload URLs, staged parameters, provider payloads/errors,
creator PII, product text, or absolute local paths.

TikTok completion means Content Posting API v2 returned
`PUBLISH_COMPLETE`. The receipt stores the async `publish_id` only as
`provider_operation_id`. A numeric public post ID is stored only when returned
by trusted status readback; an official share URL is optional and must match
that ID. Never treat `publish_id` as `post_id` and never synthesize a URL from a
username.

Shopify completion means the exact Video GID reached `READY`, was referenced
from the exact Product GID, and the association was read back. The receipt
scope is `shopify_product_media`; `post_id` and `post_url` remain null, and
public storefront visibility is not claimed.

A safe partial receipt may be persisted for post-consume `failed` or
`ambiguous` outcomes. It records only facts already observed about the same
operation/resource and never creates a post projection. Historical published
rows with no receipt remain readable as legacy/unverified but cannot authorize
the legacy status route.

## Readback and legacy status

Use `GET /distribution/publish-attempts/{attempt_id}` with
`artifact:publish|all` for tenant-bound durable readback. It returns only safe
attempt, receipt, status, error, consume/retry, post projection, and timestamp
fields. It performs no external call and no database write.

`GET /distribution/status/{platform}/{post_id}` is deprecated. It only reads an
exact durable TikTok receipt for the authenticated tenant. Shopify returns
`410 distribution_status_route_deprecated`; a missing TikTok receipt returns
404; contradictory matches or malformed durable data return 503. The route
never calls a connector and never treats the public post ID as a publish
operation ID.

## No-retry incident response

1. Record the safe attempt ID, tenant, stable code, attempt state, and whether
   acceptance consumption is proven. Do not copy raw provider responses.
2. For `preflight_failed`, verify that no consume occurred before correcting
   configuration, options, scopes, product ID, or media.
3. For any consumed `failed`, `ambiguous`, or unknown terminal state, block
   automation for that exact artifact/platform pair.
4. Inspect durable attempt readback. If external reconciliation is later
   authorized, reconcile the same operation/resource; do not initialize a new
   mutation as a diagnostic step.
5. Never automatically retry a mutation, create a replacement acceptance,
   restore a consumed acceptance, delete a remote resource, or remove a
   Shopify reference.

TikTok chunk PUTs are ordered parts of one initialized upload and are not
independent publish retries. Bounded polling observes the same operation or
resource only.

## Safe local rollback

For local-only rollback, disable both publish flags, keep the publish routes
blocked, and roll application code back without deleting receipt columns or
rewriting attempt/acceptance rows. Do not downgrade the database while code
that reads or writes receipts is running. Preserve all ambiguous and consumed
records for later reconciliation.

Never roll production back to a version that fabricates mock success, permits
legacy credential fallback, calls external status from the deprecated route,
or writes `published` without a strict receipt.

## Future deployment order

Deployment is a separately authorized change. When authorized, use this order:

1. verify a backup and restore procedure with the matching PostgreSQL 18
   client;
2. migrate the production schema while publish mutations remain blocked;
3. deploy code with both publish flags still off;
4. run no-token health, auth, route, schema, and durable readback checks;
5. provision only canonical secret names through the approved secret manager;
6. enable one platform only for the exact W1-26 pilot window;
7. perform one authorized publish and human receipt/visibility review;
8. disable the flag again until acceptance evidence is recorded.

Schema migration, deployment, credential provisioning, flag changes, and the
live publish are separate approval boundaries.

## Exact W1-26 authorization gate

No live mutation may run unless the owner explicitly authorizes all of the
following in the same bounded execution:

- one tenant, platform, acceptance UUID4, and exact reviewed artifact;
- one exact TikTok options set or Shopify Product GID;
- one approved credential source and target environment;
- one provider mutation attempt with automatic retry disabled;
- a deletion, unpublish, or Shopify reference-removal plan;
- a named human reviewer and acceptance record for receipt and visibility;
- an explicit stop rule for any ambiguous outcome.

Credential presence, a green local suite, a deployed route, or
`RUN_LIVE_PUBLISH=1` alone is not authorization. Until the full gate is
approved, retain: `provider_call=false`, `provider_attempt_made=false`,
`real_connector_call=false`, `external_status_call=false`,
`live_publish=false`, and `live_send=false`.

## Local verification

Use fixture credentials and injected transports only:

```bash
.venv/bin/python -m pytest -q \
  tests/test_publish_request_options.py \
  tests/test_publish_receipt_contracts.py \
  tests/test_publish_preflight.py \
  tests/test_tiktok_direct_post_protocol.py \
  tests/test_shopify_media_protocol.py \
  tests/test_publish_attempt_readback.py
.venv/bin/ruff check src tests
git diff --check
```

The test process must reject construction of an un-injected network client and
socket escapes. Local SQLite or disposable PostgreSQL 18 writes are test-only
and must never point at production.
