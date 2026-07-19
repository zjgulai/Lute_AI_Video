---
title: Publish acceptance consumption
doc_type: workflow
module: backend
topic: publish-acceptance-consumption
status: stable
created: 2026-07-13
updated: 2026-07-14
owner: self
source: human+ai
---

# Publish acceptance consumption

## 1. Trigger conditions and scope

Use this runbook when an authenticated publish request fails, a publish attempt
remains in `prepared` or `acceptance_consumed`, the acceptance consume result is
uncertain, or an operator is preparing a future migration, rollback, or
separately authorized live-publish check.

W1-23 binds one exact W1-22 human acceptance to one platform and one publish
attempt. It covers the canonical and deprecated HTTP adapters, durable attempt
correlation, internal single-use consume, connector invocation ordering, and
safe error projection. It does not add a review UI, public consume endpoint,
multi-platform batch, automatic retry, delivery confirmation, or production
deployment.

## 2. Permission boundary

Both mutation routes retain mount-level `verify_api_key` and require
`artifact:publish` or `all`. `artifact:accept` authorizes review-record
create/read/revoke only; it cannot publish. `provider:submit` authorizes
generation submission only; it cannot publish. Combining those narrower
permissions in a request body does not create publish authority.

The server derives tenant and principal identity from `AuthContext`. The body
cannot supply an artifact path, human-approval assertion, reviewer, tenant, or
consumer identity. There is no HTTP consume route. One acceptance authorizes
one platform only; a different platform or another live attempt needs a new
human acceptance.

## 3. Canonical and deprecated API

Canonical request:

```http
POST /distribution/publish
X-API-Key: <publisher-key>
Content-Type: application/json
```

Deprecated adapter:

```http
POST /publish/{video_id}
X-API-Key: <publisher-key>
Content-Type: application/json
```

`video_id` is a bounded compatibility label and is never authority. Both
routes accept the same strict, required body and call the same service:

```json
{
  "acceptance_id": "3f4b5088-4138-47c6-96ae-c918b8297010",
  "platform": "tiktok",
  "metadata": {
    "title": "Approved campaign video",
    "description": "One acceptance-bound publish attempt",
    "hashtags": ["approved", "campaign"],
    "tags": []
  },
  "platform_options": {
    "platform": "tiktok",
    "privacy_level": "SELF_ONLY",
    "disable_comment": true,
    "disable_duet": true,
    "disable_stitch": true,
    "brand_content_toggle": false,
    "brand_organic_toggle": true
  }
}
```

Success is one object, never a platform array:

```json
{
  "publish_attempt_id": "91ec3593-cc3c-42bf-99ee-c98655c5826b",
  "acceptance_id": "3f4b5088-4138-47c6-96ae-c918b8297010",
  "platform": "tiktok",
  "status": "published",
  "success": true,
  "post_id": "1234567890123456789",
  "post_url": "https://www.tiktok.com/@brand/video/1234567890123456789",
  "receipt": {
    "schema_version": "publish-receipt.v1",
    "platform": "tiktok",
    "protocol_version": "tiktok-content-posting-v2",
    "completion_scope": "tiktok_direct_post",
    "provider_operation_id": "v_pub_file_20260714_01",
    "provider_resource_id": "1234567890123456789",
    "target_id": null,
    "provider_status": "PUBLISH_COMPLETE",
    "post_id": "1234567890123456789",
    "post_url": "https://www.tiktok.com/@brand/video/1234567890123456789",
    "public_visibility_verified": true,
    "observed_at": "2026-07-14T08:00:00Z",
    "verified_by": "video_query",
    "simulated": false
  },
  "acceptance_consumed": true,
  "retry_allowed": false
}
```

All controlled responses from the deprecated adapter include
`Deprecation: true` and
`Link: </distribution/publish>; rel="successor-version"`. Validation errors
contain only sanitized `type`, `loc`, and `msg` fields.

## 4. Attempt state machine

The only W1-23 transitions are:

```text
prepared
  -> authorization_failed
  -> preflight_failed
  -> acceptance_consumed
       -> published
       -> failed
       -> ambiguous
```

The service checks local connector readiness before creating `prepared`, then
inspects acceptance/artifact truth and performs one read-only connector
preflight before consume. Deterministic or unavailable preflight writes
`preflight_failed` and leaves acceptance unconsumed. A successful preflight
uses the same retained connector/snapshot through consume and exactly one
publish invocation. The service persists `acceptance_consumed` before mutation
and writes terminal status, receipt, post projection, and stable error in one
compare-and-set. A terminal row never re-enters the workflow.

## 5. Acceptance and attempt error tables

Acceptance-related errors preserve the W1-22 stable codes:

| HTTP | Code | `acceptance_consumed` | `retry_allowed` | Operator meaning |
|---:|---|---:|---:|---|
| `404` | `acceptance_not_found` | `false` | `false` | Tenant-safe source/record lookup failed; do not enumerate or reuse. |
| `409` | `acceptance_expired` | `false` | `false` | Create a new review decision; expiry never reopens. |
| `409` | `acceptance_not_available` | `false` | `false` | Rejected, revoked, consumed, or concurrent loser; do not reuse. |
| `409` | `acceptance_artifact_integrity_mismatch` | `false` | `false` | Exact accepted bytes changed or disappeared; review the new artifact. |
| `503` | `acceptance_store_unavailable` | `false` | `true` | Read-only inspection proved still available; retry is manual after recovery. |

Attempt/connector errors use only these stable projections:

| HTTP | Code | `acceptance_consumed` | `retry_allowed` | Operator meaning |
|---:|---|---:|---:|---|
| `503` | `publish_connector_not_ready` | `false` | `true` | Known mock/missing configuration before attempt; remediate, then act explicitly. |
| `503` | `publish_attempt_store_unavailable` | `false` | `true` | `prepared` was not durably created; recover store before an explicit request. |
| `500` | `publish_artifact_unavailable_after_consume` | `true` | `false` | Artifact resolution failed after consume; no connector call and no reuse. |
| `500` | `publish_attempt_state_unknown` | `false`, `true`, or `null` | `false` | Durable consume/attempt truth cannot be safely projected; correlate manually. |
| `502` | `publish_connector_failed` | `true` | `false` | Connector explicitly returned `success=false`; acceptance stays consumed. |
| `502` | `publish_outcome_ambiguous` | `true` | `false` | Timeout, exception, or malformed result after the external attempt. |

For `publish_attempt_state_unknown`, the three consume projections are exact:

- `acceptance_consumed=false`: consume is proven not to have completed for this attempt, but the `authorization_failed` attempt-state write is uncertain.
- `acceptance_consumed=true`: consume by this attempt is proven, but a later attempt-state write or projection is uncertain.
- `acceptance_consumed=null`: the consume outcome itself cannot be proven.

All three projections keep `retry_allowed=false`. In particular, `false` here
does not authorize an automatic retry or acceptance restore: the operator must
correlate the stable error detail and durable rows before any separately
authorized action.

Auth `401`, permission `403`, and sanitized validation `422` happen before
acceptance consumption. Error detail contains only `code`, bounded
`publish_attempt_id`, `acceptance_consumed`, and `retry_allowed`; connector
messages, raw exceptions, paths, credentials, and request bodies stay out.

## 6. Uncertain consume outcome

An `acceptance_store_unavailable` exception is not proof that consume failed.
The service performs one bounded, read-only inspection using tenant,
acceptance ID, consumer operation, and `consumed_by_resource_id` (the
`publish_attempt_id`):

| Inspection truth | Response projection | Connector |
|---|---|---:|
| `available_not_consumed` | `acceptance_consumed=false`, `retry_allowed=true` | `0` |
| `consumed_by_this_attempt` | `acceptance_consumed=true`, `retry_allowed=false` | `0` |
| `consumed_by_another_attempt` / `not_available` | `acceptance_consumed=false`, `retry_allowed=false` | `0` |
| `unknown` | `acceptance_consumed=null`, `retry_allowed=false` | `0` |

`null` means the outcome is not safely knowable. It is never permission to
retry, restore, consume again, or call the connector.

## 7. No automatic retry and no restore

The backend and frontend perform **no automatic retry** for publish. There is
also **no restore** of an acceptance after consume, connector failure, timeout,
ambiguous result, process crash, or audit-update failure. A retryable pre-consume
error permits only a later explicit operator request after remediation.

If consume might have succeeded, the same acceptance is fail-closed forever.
Another real publish attempt requires a new human acceptance. Do not replay an
old request, edit the ledger, or change `retry_allowed` based on platform UI
guesswork.

## 8. Stale-row manual correlation

For a stale `prepared` row, read the tenant-bound publish attempt and the
acceptance record. Compare the attempt ID with acceptance
`consumed_by_resource_id` and require
`consumed_by_operation=distribution.publish`:

- acceptance still `available`: no automatic worker resume; after store and
  connector readiness are healthy, an operator may issue a new explicit
  request and create a new attempt;
- consumed by this attempt: do not call the connector, do not restore, and
  preserve the stale row as audit truth;
- consumed by another attempt or conflicting consumer metadata: stop and
  correlate the other attempt;
- missing, malformed, or unavailable storage: classify as unknown and stop.

For stale `acceptance_consumed`, correlate platform audit/receipt evidence and
the attempt row. Never infer `published` merely from a timeout or manually
rewrite the terminal state. W1-26 owns separately authorized live evidence.

## 9. Rollback

Forward production activation, if separately authorized later, follows:

```text
verified backup -> schema migration -> application rollout
```

Rollback is route-block-first:

```text
block both mutation routes -> deploy a safe application -> optional schema downgrade
```

Block both `POST /distribution/publish` and `POST /publish/{video_id}` before
starting old code. The additive nullable publish columns may remain while a safe
application runs. Consider schema downgrade only after verifying no required
W1-23 audit data would be lost. Never roll old code back first, and never use a
schema downgrade as an application rollback.

## 10. Residual work and evidence ceiling

- The accepted artifact is mutable on disk after the W1-22 hash check; an
  immutable object/version snapshot remains deferred.
- W1-24 connector fail-closed behavior and W1-25 protocol/receipt calibration
  are implemented with local fake-transport and disposable-database evidence;
  neither is a real-platform acceptance claim.
- Delivery, real receipt/visibility acceptance, reconciliation, and active-post
  semantics remain external W1-26 work.
- There is no W1-23 acceptance/publish UI; callers without a real acceptance ID
  fail locally with zero network mutation.
- W1-26 owns the separately authorized live publish acceptance run.
- Production still needs an approved backup, migration, permission assignment,
  application rollout, and read-only verification before any live mutation.

`W1-23 completed_local` is not live publish evidence and is not production
acceptance. Historical 12/13/14-table records remain dated evidence; the current
recovery order is the ordered 16-table contract, including the current `publish_logs`
correlation columns and the provider-cost ledger tables.

## 11. Local verification and boundary tags

Safe local checks:

```bash
.venv/bin/python -m pytest \
  tests/test_backend_route_auth_contract.py \
  tests/test_backup_production_contract.py \
  tests/test_run_alembic_upgrade.py \
  tests/test_openapi_types_drift_guard.py -q

.venv/bin/python -m pytest tests/test_publish_e2e.py --collect-only -q
```

The second command is collection only. Do not execute the live test in W1-23.
Its later W1-26 execution requires `RUN_LIVE_PUBLISH=1`, one exact UUID4
`LIVE_PUBLISH_ACCEPTANCE_ID`, one `LIVE_PUBLISH_PLATFORM`, an explicit
`LIVE_PUBLISH_API_KEY`, and separate owner authorization.

Current boundary tags: `local_only`, `production unchanged`,
`provider_call=false`, `provider_attempt_made=false`,
`connector_call=fake-only`, `real_connector_call=false`,
`external_status_call=false`, `live_publish=false`,
`database_write=local-test-only`,
`production database_write=false`. No production migration, deploy, provider generation,
connector mutation, publish, delivery, SSH, stage, commit, push, or PR is part
of this evidence.
