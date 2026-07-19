# Publish Acceptance Consumption Design

**Status:** Approved on 2026-07-12; implementation and local acceptance completed on 2026-07-13 with the `completed_local` evidence ceiling.

**Roadmap scope:** W1-23 only. W1-24/W1-25 connector credential and receipt truth, W5 acceptance UI and rubric, W1-26 live publish, immutable artifact snapshots, production migration, and deployment remain separate work.

**Evidence boundary:** Local design, implementation, fake connectors, fixtures, disposable PostgreSQL 18 checks, tests, builds, and independent review may reach `L2-fixture-or-dry-run` and the project state `completed_local`. This specification does not authorize a production migration, SSH connection, deploy, provider call, real publish, delivery, production write, off-host transfer, commit, push, or PR.

## 1. Problem and required outcome

The two current publish routes trust caller-controlled authority and artifact data:

- `POST /distribution/publish` accepts nested human-acceptance assertions and caller content;
- `POST /publish/{video_id}` accepts the same assertions, accepts caller `metadata.video_path`, or searches `OUTPUT_DIR` by the caller path parameter;
- the legacy route can fan one request out to several platforms;
- both routes use general API-key verification rather than a publish-specific permission;
- publish logging is best-effort and is not tenant- or acceptance-correlated.

W1-22 already created the server-owned, tenant-bound, exact-byte, single-use acceptance authority and the internal `consume_for_publish(...)` boundary. W1-23 must make that boundary the only authority for an external publish attempt.

The required outcome is:

1. one authenticated tenant requests one supported platform and one acceptance ID;
2. all predictable validation and connector-readiness checks finish before acceptance consumption;
3. the server durably creates one publish-attempt record;
4. W1-22 atomically consumes the acceptance for that exact server attempt;
5. the server invokes exactly one connector at most once;
6. when the process remains alive through terminal handling and the store succeeds, the server durably records `published`, deterministic `failed`, or `ambiguous` truth; otherwise the active row is explicitly unresolved evidence requiring manual reconciliation;
7. a failure after consume never restores the acceptance and never triggers an automatic retry;
8. neither request-body human claims, client paths, filesystem search, nor a URL path parameter can grant publish authority.

## 2. Scope

### 2.1 In scope

W1-23 covers:

- canonical `POST /distribution/publish`;
- deprecated compatibility `POST /publish/{video_id}`;
- strict request, response, and safe error models;
- `artifact:publish` permission recognition and enforcement;
- a shared `PublishAttemptService` used by both routes;
- one platform per acceptance and per request;
- exact accepted Fast or S1-S5 final-video bytes obtained from W1-22 consume output;
- narrow no-network connector-readiness inspection before consume;
- a specialized fail-closed publish-attempt repository over the existing `publish_logs` table;
- additive PostgreSQL/Alembic, fresh-init SQL, and existing/fresh SQLite parity;
- generated OpenAPI TypeScript types and frontend zero-network guards;
- fake-connector, concurrency, failure-injection, migration, regression, full-quality, and independent-review evidence;
- documentation and roadmap synchronization after implementation acceptance.

### 2.2 Explicit non-goals

W1-23 does not:

- call a real TikTok or Shopify API during development or local acceptance;
- add an asynchronous publish worker, queue, scheduler, or background retry;
- create a multi-platform batch, partial-success ledger, or batch retry state machine;
- add an HTTP acceptance-consume endpoint;
- add a human-review, acceptance-selection, or publish-attempt history UI;
- issue or mutate production API keys or assign production permissions;
- make connectors fail closed internally for every credential error or normalize simulated receipts; those are W1-24/W1-25;
- prove TikTok or Shopify delivery, public visibility, deletion, rollback, or active-post metrics;
- copy the accepted file into immutable attempt-owned storage;
- remove the current host-local exact-byte time-of-check/time-of-use boundary;
- backfill legacy `publish_logs` rows or treat them as publish authority;
- migrate, deploy, or inspect production through SSH;
- alter read-only `/distribution/status/{platform}/{post_id}` or `/distribution/platforms` behavior.

## 3. Current-state facts that constrain the design

Repository inspection establishes these implementation facts:

- `src/routers/distribution.py` contains exactly two HTTP publish mutations;
- `_require_human_publish_authorization(...)` trusts body fields such as `source=human`, reviewer text, `delivery_accepted`, and `publish_allowed`;
- `PublishEngine.publish(...)` loops over a platform list and catches connector exceptions inside its per-platform methods;
- `src.connectors.registry.publish_to_platform(...)` invokes exactly one connector and does not itself catch exceptions, although current connector internals still convert some timeout/exception paths into `success=false` results;
- TikTok and Shopify expose existing no-network `_is_mock_mode()` checks;
- W1-22 `ArtifactAcceptanceService.consume_for_publish(...)` reopens and re-hashes the stored canonical artifact, then performs a tenant-bound compare-and-set from `available` to `consumed`;
- the consume output includes the server-owned source identity, scenario, canonical relative path, exact SHA-256, byte size, and kind;
- PostgreSQL fresh init lacks `publish_logs.tenant_id`; SQLite already has nullable `tenant_id`; neither schema has `acceptance_id` or `updated_at` for this attempt lifecycle;
- generic `PublishLogRepository` is neither tenant-scoped nor a compare-and-set state repository;
- current frontend callers have no acceptance ID, and some still construct client path/URL metadata;
- W1-22 is local-only and production has not been migrated for acceptance records.

These facts make a route-only patch insufficient. Authority, call order, persistence, concurrency, frontend behavior, and error truth must move together.

## 4. Security and authority invariants

The following invariants are mandatory:

1. `tenant_id` comes only from authenticated `AuthContext`.
2. Publishing requires `artifact:publish` or `all`.
3. A key carrying only `artifact:accept` or only `provider:submit` cannot publish.
4. `acceptance_id` is the only request field that names publish authority.
5. One accepted record authorizes exactly one platform and one external connector invocation attempt.
6. The platform is an exact enum, not a case-normalized or caller-extended string.
7. The request cannot supply an artifact path, URL, digest, size, scenario, source resource, reviewer, tenant, human decision, delivery decision, publish decision, or attempt ID.
8. Both HTTP routes invoke the same service and persistence path.
9. The legacy `video_id` path parameter never selects, searches for, verifies, or authorizes a file.
10. Body and metadata validation, permission checks, and connector readiness finish before durable attempt creation and before acceptance consumption.
11. The durable `prepared` row exists before acceptance consumption.
12. The W1-22 compare-and-set is the only consume authority; a read response is not sufficient.
13. The connector is never called unless consume returned success and the attempt row was durably advanced to `acceptance_consumed`.
14. At most one connector invocation occurs for an accepted record under concurrent requests.
15. No code path automatically retries a publish mutation.
16. A consumed acceptance is never restored to `available`, including connector failure, timeout, exception, audit-store failure, process crash, or ambiguous client response.
17. Production publish attempt persistence fails closed when PostgreSQL or the required schema is unavailable.
18. Logs, rows, responses, and exceptions never contain API keys, connector credentials, raw request bodies, host absolute paths, or secret values.
19. A mock or known missing-credential connector state fails before consume.
20. W1-23 local success does not prove W1-24/W1-25 connector-internal truth or W1-26 live publish.
21. A consume-store exception is not proof that consume did not occur; no connector or same-acceptance retry is permitted until a bounded internal read proves the acceptance remained available.

## 5. Permission and authenticated principal

Add `artifact:publish` to `_RECOGNIZED_TENANT_PERMISSIONS`.

Both mutation routes use `Depends(require_permission("artifact:publish"))` and receive the resolved `AuthContext`:

| Principal permission | Publish behavior |
|---|---|
| `artifact:publish` | Allowed to enter strict validation and service orchestration |
| `all` | Allowed through the existing super-permission rule |
| `artifact:accept` only | `403` before readiness, persistence, consume, or connector work |
| `provider:submit` only | `403` before readiness, persistence, consume, or connector work |
| malformed or unknown permission set | Normalizes to no permissions and is denied |

The attempt persists the authenticated tenant ID. It does not persist a request-body actor or reviewer. Reviewer identity remains linked through the server-owned acceptance record.

This batch only recognizes and enforces the new permission. Production key issuance, assignment, rotation, and operator mapping require separate authorization.

## 6. Canonical HTTP contract

### 6.1 Request model

`POST /distribution/publish` accepts exactly:

```json
{
  "acceptance_id": "7f947625-2898-4e9e-9e71-dce4309e5f4f",
  "platform": "tiktok",
  "metadata": {
    "title": "Hands-free pumping for a busy day",
    "description": "Reviewed final campaign video.",
    "hashtags": ["momlife", "wearablepump"],
    "product_name": "Wearable Breast Pump"
  }
}
```

The top-level model is strict and forbids extra fields:

- `acceptance_id`: exact lower-case UUID text generated by W1-22;
- `platform`: exact `tiktok|shopify`;
- `metadata`: required object; may be empty; extra fields are forbidden.

The request therefore rejects `platforms`, `content`, `video_id`, `video_path`, `video_url`, `thumbnail_url`, `delivery_acceptance`, `source`, `reviewer`, `delivery_accepted`, `publish_allowed`, `tenant_id`, `scenario`, `artifact_path`, `post_id`, and all other unknown fields with safe `422` output before service work.

### 6.2 Metadata allowlist and safety caps

The metadata object permits only:

| Field | Type | Bound |
|---|---|---|
| `title` | optional strict string | 1-300 characters after trimming |
| `description` | optional strict string | 1-5000 characters after trimming |
| `hook` | optional strict string | 1-1000 characters after trimming |
| `product_name` | optional strict string | 1-300 characters after trimming |
| `hashtags` | optional strict string list | at most 30 items; each 1-100 characters |
| `tags` | optional strict string list | at most 30 items; each 1-100 characters |

Metadata rules:

- strings containing null bytes or control characters are rejected;
- tag items are trimmed, must not include a leading `#`, and must be unique within their list;
- if both `hashtags` and `tags` are supplied, each is preserved but platform mapping uses the precedence defined below;
- the canonical UTF-8 JSON representation of metadata must not exceed 16 KiB;
- no coercion from numbers, booleans, objects, or delimited strings is allowed;
- absent optional values remain absent rather than becoming request authority.

These are application safety caps, not claims about every current or future platform limit. Connector- and platform-specific policy validation can become stricter later without weakening this authority boundary.

### 6.3 Safe manual parsing and OpenAPI

The route reads `Request` JSON and validates it manually with the same strict Pydantic model used to generate JSON Schema. This follows the existing W1-22 pattern:

- invalid JSON returns `422` with `type`, `loc`, and `msg` only;
- Pydantic errors are projected to `type`, `loc`, and `msg` only;
- `input`, `ctx`, `url`, raw bodies, and field values are never echoed;
- `openapi_extra.requestBody` uses `PublishAttemptRequest.model_json_schema(mode="validation")`;
- generated OpenAPI must mark the request body required and expose no `requestBody?: never` drift.

FastAPI documents `openapi_extra` as the low-level path for manually validated request bodies that still need an OpenAPI request schema. Pydantic strict mode and `extra='forbid'` provide the required no-coercion and unknown-field rejection behavior.

References:

- <https://fastapi.tiangolo.com/advanced/path-operation-advanced-configuration/>
- <https://docs.pydantic.dev/latest/concepts/strict_mode/>
- <https://docs.pydantic.dev/latest/api/config/>

### 6.4 Successful response

A connector success that is durably persisted returns HTTP `200`:

```json
{
  "publish_attempt_id": "91ec3593-cc3c-42bf-99ee-c98655c5826b",
  "acceptance_id": "7f947625-2898-4e9e-9e71-dce4309e5f4f",
  "platform": "tiktok",
  "status": "published",
  "success": true,
  "post_id": "fixture-post-1",
  "post_url": "https://example.invalid/posts/fixture-post-1",
  "acceptance_consumed": true,
  "retry_allowed": false
}
```

The normal application response wrapper may add `_meta`. The response never exposes tenant ID, artifact path, digest, byte size, reviewer identity, credentials, or connector request payload.

`post_id` must be a strict control-free string of at most 256 characters. `post_url`, when present, must be an `http|https` URL of at most 2048 characters with no user-info, query, or fragment. A success response that cannot satisfy this safe projection is indeterminate and follows the `ambiguous` path rather than persisting or returning an unsafe value.

For W1-23, explicit connector `success=true` is sufficient for the local service state transition. W1-24/W1-25 still own simulated-result labeling, complete credential fail-closed behavior, and strong real-receipt validation; therefore local `published` fixture evidence is not a production publish claim.

## 7. Server-owned connector payload

After successful consume, `PublishAttemptService` builds the connector content from two sources only:

- W1-22 consume output supplies the exact canonical artifact path and source identity;
- the strict allowlisted metadata model supplies descriptive fields.

The service resolves the canonical relative artifact path through the shared tenant artifact resolver below configured `OUTPUT_DIR`. It passes the resolved host path only in memory to the connector and never persists or returns that absolute path.

Platform mapping is deterministic:

### TikTok

- `video_path`: server-resolved accepted artifact path;
- `title`: `metadata.title`, otherwise `metadata.hook`, otherwise `AI-generated video`;
- `tags`: `metadata.hashtags` when non-empty, otherwise `metadata.tags`, otherwise an empty list;
- `description`: explicit `metadata.description`, otherwise `metadata.hook`, otherwise the chosen title; append the selected tags once as `#tag` tokens separated by spaces;
- `product_name`: not forwarded unless a future connector contract requires it.

### Shopify

- `video_path`: server-resolved accepted artifact path;
- `title`: `metadata.title`, otherwise `metadata.hook`, otherwise `AI-generated video`;
- `product_name`: explicit `metadata.product_name`, otherwise the chosen title;
- `description`, `tags`, and `hashtags`: not forwarded because the current Shopify connector contract does not consume them.

Both routes call the single-platform registry boundary rather than `PublishEngine.publish(...)`. This prevents hidden fan-out and preserves exceptions that reach the orchestration boundary for deterministic-versus-ambiguous classification. Current connector-internal exception-to-failure conversion remains a W1-24 truth gap and must be stated in the local verdict.

## 8. Shared service architecture

Introduce a single orchestration service, conceptually:

```text
HTTP adapter
  -> strict body and permission
  -> connector readiness
  -> PublishAttemptRepository.create_prepared
  -> ArtifactAcceptanceService.consume_for_publish
  -> PublishAttemptRepository.mark_acceptance_consumed
  -> one injected connector call
  -> PublishAttemptRepository.mark_published|mark_failed|mark_ambiguous
  -> typed HTTP projection
```

Both route adapters pass:

- authenticated `AuthContext`;
- strict request model;
- route kind for observability only (`canonical` or `legacy_adapter`).

The service owns the server-generated UUID `publish_attempt_id`. It passes:

- `consumer_operation="distribution.publish"`;
- `consumer_resource_id=<publish_attempt_id>`

to W1-22 `consume_for_publish(...)`.

The route never calls the acceptance repository directly. The connector never receives `acceptance_id`, tenant ID, reviewer identity, or an authority object.

Dependencies for the acceptance service, consume-outcome inspector, attempt repository, readiness inspector, artifact resolver, and connector caller are injectable so tests can prove ordering and side-effect counts without environment credentials or network access.

The consume-outcome inspector is an internal read-only W1-22 service boundary, not an HTTP endpoint and not publish authority. Given tenant, acceptance ID, consumer operation, and attempt ID, it validates the stored row and returns only one of:

- `available_not_consumed`;
- `consumed_by_this_attempt`;
- `consumed_by_another_attempt`;
- `not_available`;
- `unknown`.

It may use the tenant-bound acceptance ID lookup and stored `consumed_by_operation`/`consumed_by_resource_id`; it does not require a new acceptance-table index or foreign key. A malformed row, projection failure, database failure, missing row after an uncertain commit, or conflicting consumer identity returns `unknown`.

## 9. Exact operation order

The service sequence is fixed:

1. require authenticated tenant and `artifact:publish|all`;
2. parse and validate strict JSON, UUID, platform, metadata, and safety caps;
3. inspect the selected connector's known mock/missing-credential readiness without network access;
4. generate `publish_attempt_id` in the server process;
5. durably insert the tenant-bound `prepared` attempt;
6. call W1-22 consume with tenant, acceptance ID, operation, and attempt ID;
7. durably compare-and-set the attempt from `prepared` to `acceptance_consumed`;
8. resolve the consumed canonical relative path below `OUTPUT_DIR` and build the allowlisted connector payload;
9. invoke exactly one connector exactly once;
10. classify explicit failure, explicit success, or ambiguous outcome;
11. durably compare-and-set the terminal attempt state;
12. return a success or typed non-retryable error.

No connector invocation may move before step 7. No predictable body, platform, metadata, permission, or known-readiness check may move after step 6.

If step 8 fails after a successful consume, the service durably marks the attempt `failed`, returns `publish_artifact_unavailable_after_consume`, does not call the connector, does not restore the acceptance, and forbids retry with the same acceptance.

If step 6 raises `AcceptanceStoreUnavailable`, the service must not assume the compare-and-set failed. It performs one bounded internal consume-outcome inspection and never calls the connector on this request:

- proven `available_not_consumed`: record `authorization_failed`, return `acceptance_store_unavailable`, and allow only a later explicit manual request after store recovery;
- proven `consumed_by_another_attempt` or `not_available`: record `authorization_failed` and return `acceptance_not_available`;
- proven `consumed_by_this_attempt`: leave the last durable attempt state unchanged, return `publish_attempt_state_unknown` with `acceptance_consumed=true`, and forbid retry;
- `unknown`: leave the last durable attempt state unchanged, return `publish_attempt_state_unknown` with `acceptance_consumed=null`, and forbid retry.

The bounded inspection is read-only recovery of truth, not a second consume and not an automatic publish retry.

## 10. Narrow connector-readiness gate

Add one no-network readiness inspector at the connector registry boundary:

- unknown platforms are already impossible after strict validation;
- TikTok readiness delegates to the current credential/mock-mode predicate;
- Shopify readiness delegates to the current credential/store/mock-mode predicate;
- the inspector returns only `ready` plus a stable reason code;
- it does not print, return, persist, hash, or compare secret values beyond the existing presence check;
- it does not issue a status request or any external network call.

Known mock or missing-credential state returns:

- HTTP `503`;
- `code=publish_connector_not_ready`;
- no attempt row;
- no acceptance consume;
- no connector call;
- `acceptance_consumed=false`;
- `retry_allowed=true` for a later explicit manual request after operator remediation;
- no automatic retry.

This is intentionally narrower than W1-24/W1-25. It prevents a known local mock path from burning acceptance but does not prove that connector-internal credential validation, receipt truth, permissions, remote platform state, or token validity are complete.

## 11. Accepted artifact resolution and remaining TOCTOU boundary

W1-22 consume already reopens the stored artifact, resolves tenant ownership, recomputes exact SHA-256 and byte size, checks integrity, and atomically consumes the record. W1-23 must use that returned canonical relative path; it cannot reintroduce `metadata.video_path`, `content.video_url`, or `OUTPUT_DIR.rglob(...)`.

After consume, W1-23 resolves that same canonical relative path through the shared resolver and passes the resulting host path to the connector. It must reject path escape, symlink escape, unsupported suffix, missing file, non-file, tenant mismatch, and malformed stored projection.

This design does not copy the accepted bytes into immutable attempt-owned storage. A same-host privileged actor could change a file after W1-22 hashes it and before the connector reopens it. This is a known exact-byte TOCTOU residual.

The local W1-23 verdict must therefore state:

- acceptance binding and consume-time integrity are enforced;
- client path authority and filesystem search are removed;
- an immutable post-consume snapshot is not implemented;
- full exact-byte publish proof remains incomplete until a later snapshot/object-version design closes this residual.

## 12. Publish-attempt persistence

### 12.1 Reuse `publish_logs`

The existing `publish_logs.id` becomes `publish_attempt_id` for new W1-23 rows. Reuse preserves existing metrics/audit consumers and avoids a second publish-intent table.

Add nullable, legacy-compatible columns:

| Column | PostgreSQL | SQLite | New-row rule |
|---|---|---|---|
| `tenant_id` | `VARCHAR(64)` | `TEXT` | required by specialized repository |
| `acceptance_id` | `VARCHAR(36)` | `TEXT` | required by specialized repository |
| `updated_at` | `TIMESTAMPTZ` | `TIMESTAMP` | required and database-time maintained |

The existing columns retain their meaning:

- `id`: server attempt ID;
- `platform`: exact selected platform;
- `status`: attempt state;
- `content`: safe audit projection;
- `post_id` and `url`: connector success projection;
- `error`: stable W1-23 code only;
- `created_at`: database creation time.

Historical rows may keep null tenant, acceptance, and updated time. They are evidence only and never authorize a new publish.

### 12.2 Indexes

Add:

```sql
CREATE INDEX idx_publish_logs_tenant_created_at
    ON publish_logs(tenant_id, created_at DESC);

CREATE INDEX idx_publish_logs_tenant_acceptance
    ON publish_logs(tenant_id, acceptance_id);
```

Do not add a unique constraint on `acceptance_id`. Multiple concurrent or pre-consume failed attempts must remain auditable; W1-22 acceptance compare-and-set remains the single-use authority.

Do not add a foreign key to `acceptance_records` in this batch. Historical rows are nullable, current backup/restore ordering treats both tables independently, and application authority already validates the tenant-bound acceptance. This avoids changing disaster-recovery ordering inside W1-23.

### 12.3 Safe audit content

The initial `prepared` row knows only server attempt identity, tenant, acceptance ID, route kind, platform, and strict metadata. It does not pre-read acceptance authority to populate source or artifact fields.

After W1-22 consume succeeds, `mark_acceptance_consumed` atomically adds the server-owned source/artifact projection while advancing the state. A post-consume or terminal `content` value contains only:

```json
{
  "schema_version": "publish-attempt.v1",
  "route_kind": "canonical",
  "source": {
    "resource_type": "scenario",
    "resource_id": "s2_1783830000_abcdef12",
    "scenario": "s2"
  },
  "artifact": {
    "path": "tenants/example/pending_review/s2_1783830000_abcdef12/assemble/final.mp4",
    "sha256": "64-lower-case-hex-characters",
    "size_bytes": 123456,
    "kind": "video"
  },
  "metadata": {
    "title": "Hands-free pumping for a busy day",
    "hashtags": ["momlife", "wearablepump"]
  }
}
```

The row does not store the raw request, API key, credential, secret, authorization header, reviewer notes, human assertion, connector error message, host absolute path, legacy `video_id`, or unknown metadata.

An `authorization_failed` row keeps only its safe pre-consume projection. If `mark_acceptance_consumed` cannot persist the source/artifact projection, the connector is not called; the consumed acceptance still identifies the attempt through `consumed_by_resource_id`.

### 12.4 Specialized repository

Add `PublishAttemptRepository`; do not extend generic `PublishLogRepository` into an authority boundary.

The specialized repository must:

- validate tenant, acceptance, attempt, platform, state, content, and timestamp shapes;
- create only the safe pre-consume content projection, then add source/artifact content in the `prepared -> acceptance_consumed` compare-and-set;
- use PostgreSQL transactions and tenant/attempt compare-and-set updates;
- use SQLite `BEGIN IMMEDIATE` plus the existing process lock for equivalent local serialization;
- fail closed in production when verified PostgreSQL or required columns are unavailable;
- never fall back from configured production PostgreSQL to SQLite, filesystem, or memory;
- return only validated row projections;
- translate driver/schema failures to a typed store-unavailable error;
- expose no method that changes `authorization_failed`, `published`, `failed`, or `ambiguous` back to an active state.

## 13. Attempt state machine

New W1-23 rows use only:

```text
prepared
  -> authorization_failed
  -> acceptance_consumed
       -> published
       -> failed
       -> ambiguous
```

Transition rules:

| From | To | Trigger | Connector count |
|---|---|---|---:|
| none | `prepared` | durable attempt insert | 0 |
| `prepared` | `authorization_failed` | typed W1-22 consume rejection | 0 |
| `prepared` | `acceptance_consumed` | consume returned success | 0 |
| `acceptance_consumed` | `published` | explicit connector `success=true`, terminal row persisted | 1 |
| `acceptance_consumed` | `failed` | deterministic post-consume artifact resolution failure or explicit connector `success=false`, terminal row persisted | 0 or 1 |
| `acceptance_consumed` | `ambiguous` | timeout, exception, malformed or indeterminate connector response, terminal row persisted | 1 |

Every update is a tenant-bound compare-and-set. A row in a terminal state cannot re-enter `prepared` or `acceptance_consumed`.

The table retains legacy status strings from historical code. No table-wide status constraint is added because it could invalidate historical rows. The specialized repository enforces the new state set for W1-23 rows.

## 14. Stable error contract

For typed attempt errors, `acceptance_consumed` means “this publish attempt is proven to have completed W1-22 consume,” not whether some other concurrent attempt consumed the same record. Its type is `true|false|null`; `null` means the consume result is not safely knowable and always implies `retry_allowed=false`.

| HTTP | Code | Condition | Attempt state | Consumed by this attempt | Same acceptance may be manually resubmitted |
|---:|---|---|---|---:|---:|
| `401` | existing auth detail | missing/invalid API key | none | false | no authority established |
| `403` | existing permission detail | lacks `artifact:publish|all` | none | false | only with a permitted principal |
| `422` | safe validation projection | invalid/extra/legacy body or metadata | none | false | after correcting request |
| `503` | `publish_connector_not_ready` | known mock/missing credential before attempt | none | false | yes, explicitly after remediation |
| `503` | `publish_attempt_store_unavailable` | `prepared` insert failed | none | false | yes, explicitly after store recovery |
| `404` | `acceptance_not_found` | W1-22 tenant-safe not found | `authorization_failed` | false | no |
| `409` | `acceptance_expired` | acceptance expired | `authorization_failed` | false | no |
| `409` | `acceptance_not_available` | acceptance rejected/revoked/already consumed/not available | `authorization_failed` | false | no |
| `409` | `acceptance_artifact_integrity_mismatch` | accepted exact bytes changed/missing | `authorization_failed` | false | no |
| `503` | `acceptance_store_unavailable` | consume-store error followed by proof that this acceptance remains available | `authorization_failed` | false | yes, explicitly after recovery |
| `500` | `publish_artifact_unavailable_after_consume` | consumed path cannot be safely resolved before connector | `failed` | true | no |
| `500` | `publish_attempt_state_unknown` | consume result cannot be safely proven, or repository update failed after prepared row | last durable state | true if proven consumed; otherwise null | no |
| `502` | `publish_connector_failed` | explicit connector `success=false`, `failed` persisted | `failed` | true | no |
| `502` | `publish_outcome_ambiguous` | timeout/exception/indeterminate response, `ambiguous` persisted | `ambiguous` | true | no |

Error detail for publish-attempt errors is bounded:

```json
{
  "code": "publish_connector_failed",
  "publish_attempt_id": "91ec3593-cc3c-42bf-99ee-c98655c5826b",
  "acceptance_consumed": true,
  "retry_allowed": false
}
```

Rules:

- a pre-attempt failure omits `publish_attempt_id`;
- W1-22 stable acceptance codes are preserved exactly;
- `AcceptanceStoreUnavailable` from consume is never projected directly until the bounded outcome inspection proves `available_not_consumed`;
- an unknown consume outcome returns `publish_attempt_state_unknown`, `acceptance_consumed=null`, and `retry_allowed=false`;
- if the `authorization_failed` audit update itself fails, return `publish_attempt_state_unknown` rather than claiming the state was persisted;
- if consume succeeds but `mark_acceptance_consumed` fails, return `publish_attempt_state_unknown`, do not call the connector, and do not restore acceptance;
- if the consumed path cannot be safely resolved after `mark_acceptance_consumed`, persist `failed`, return `publish_artifact_unavailable_after_consume`, do not call the connector, and do not restore acceptance;
- if final persistence fails after a connector return or exception, return `publish_attempt_state_unknown`; the connector has already been invoked, so retry remains forbidden;
- explicit connector failure is different from timeout, exception, missing success truth, or malformed response;
- connector exception text and connector-reported error text are neither persisted nor returned; logs record only the stable code, attempt ID, platform, trace ID, and exception class name, never `str(exc)` or a raw connector message.

## 15. Concurrency, ambiguity, and crash semantics

### 15.1 Concurrent requests

Concurrent requests may each create a `prepared` audit row. Only one W1-22 consume compare-and-set can win:

- the winner advances to `acceptance_consumed` and may invoke one connector;
- every loser records `authorization_failed` and returns `acceptance_not_available`;
- connector invocation count across the cohort is exactly one;
- no unique `publish_logs.acceptance_id` index substitutes for the W1-22 authority transition.

### 15.2 Client retries

Mutation helpers and the backend perform zero automatic retries.

If a client response is lost:

- retry before consume may create a new attempt and proceed because no external attempt was authorized yet;
- retry after consume loses W1-22 compare-and-set and cannot call the connector;
- a connector timeout is treated as externally ambiguous even if local evidence suggests no post was created;
- another live attempt requires a newly created human acceptance record.

A consume-store exception follows the bounded outcome inspection above. The client cannot retry the same acceptance unless the server explicitly proved `available_not_consumed`; absence of proof is an unknown, non-retryable state.

W1-23 does not add an idempotency key to publish. The consumed acceptance and attempt audit correlation are the authority boundary. A replayable mutation contract would require a separate external-result reconciliation design.

### 15.3 Process crash windows

| Crash point | Durable truth | Recovery rule |
|---|---|---|
| before `prepared` insert | no attempt; acceptance available | explicit request may be tried later |
| after `prepared`, before consume | `prepared`; acceptance available | no worker resume; explicit request may be tried later |
| after consume, before `acceptance_consumed` update | acceptance consumed; row may remain `prepared` | no connector; no restore; operator inspects acceptance consumer ID |
| after `acceptance_consumed`, before connector | acceptance consumed; row active | no automatic resume or retry |
| during connector call | external outcome unknown | no retry; record should become `ambiguous` if process survives |
| after connector return, before terminal persistence | connector invoked; row may remain active | no retry; operator reconciliation required |
| after terminal persistence, before HTTP response | terminal row and consumed acceptance | retry cannot invoke connector again |

No crash-recovery worker is introduced in this batch. A stale `prepared` or `acceptance_consumed` row is nonterminal evidence requiring manual correlation with the acceptance consumer identity and platform state. It is not permission to resume an external mutation and is not proof that every external outcome was durably classified.

## 16. Deprecated legacy route

`POST /publish/{video_id}` remains temporarily mounted as a compatibility adapter but changes to the same strict `PublishAttemptRequest` body and the same single `PublishAttemptResponse` result.

Legacy adapter rules:

- OpenAPI marks the operation `deprecated=true`;
- the response includes `Deprecation: true` and a successor link to `/distribution/publish`;
- no sunset date is invented before an owner-approved removal schedule exists;
- `video_id` must satisfy a bounded safe path-parameter grammar but is otherwise ignored for authority and file lookup;
- the value is not persisted in the attempt row;
- the body uses `platform`, not `platforms`;
- `platforms=[]`, duplicate values, multiple values, old `metadata.video_path`, old body human claims, and old `content` shape return safe `422`;
- the route never constructs or invokes `PublishEngine.publish(...)`;
- both routes return identical typed success and error semantics.

This intentionally preserves the route location for a bounded transition while breaking unsafe authority and fan-out compatibility.

## 17. Frontend compatibility boundary

W1-23 updates API helpers and tests but adds no acceptance UI.

### `publishContent(...)`

- adds optional `acceptanceId` inside the existing options object;
- validates the lower-case UUID before constructing a request;
- validates one exact platform;
- validates the same metadata allowlist and rejects unknown fields rather than silently dropping them;
- throws a stable local error before `apiFetch` when acceptance is absent or invalid;
- sends the strict canonical request only when acceptance exists.

### `publishVideo(...)`

- keeps the legacy helper signature long enough to avoid unrelated component rewrites;
- adds optional `acceptanceId` inside its options object;
- requires `platforms.length === 1` before `apiFetch`;
- maps the one value to body `platform`;
- validates the same metadata allowlist and rejects unknown fields;
- never sends the `videoId`, client path, `platforms` array, or unknown metadata in the body;
- uses the deprecated route only as a path-compatibility adapter;
- throws locally when acceptance is absent, so current UI callers make zero publish POSTs.

Current `PublishPanel`, `PublishFlow`, `DistributionView`, and `OneShotResultView` do not possess a W1-22 acceptance ID. Their publish actions therefore fail closed locally and show the existing error surface. W1-23 does not fake an ID, read arbitrary acceptance records, infer authority from video paths, or add an acceptance picker.

Frontend tests must spy below the helpers and prove missing acceptance, invalid acceptance, zero/multiple platforms, and unsafe legacy metadata cause zero network calls.

## 18. Migration and schema parity

Create one reversible Alembic revision descending from `e8f1a2b3c4d5`. It performs only additive changes to `publish_logs` and the two indexes.

Synchronize three schema paths:

1. Alembic upgrade/downgrade for existing PostgreSQL;
2. `src/storage/migrations/001_init.sql` for fresh PostgreSQL and reused init volumes;
3. `src/storage/db.py` create-table plus `_ensure_sqlite_compat_columns()` for fresh and existing SQLite.

Migration rules:

- all three columns remain nullable at table level for legacy rows;
- new repository writes require non-null tenant, acceptance, and updated time;
- no legacy row backfill is required;
- no table-wide status constraint is added;
- backup required-table count and recovery ordering remain unchanged because no table is added;
- storage readiness verifies the required `publish_logs` W1-23 columns before declaring publish-attempt persistence ready;
- schema/restore tests must assert the new columns and indexes;
- downgrade drops W1-23 indexes before columns and does not delete historical rows;
- a future authorized upgrade takes a fresh backup, applies and verifies schema first, then deploys the W1-23 application;
- application rollback occurs before schema downgrade.

PostgreSQL supports additive columns through `ALTER TABLE`. Normal index creation can block writers, while `CREATE INDEX CONCURRENTLY` has different transaction and failure behavior. Local implementation uses disposable PostgreSQL 18 to prove schema correctness only. A later production migration must inspect table size, assess lock impact, select a maintenance strategy, take a fresh backup, and receive explicit authorization before execution.

References:

- <https://www.postgresql.org/docs/18/ddl-alter.html>
- <https://www.postgresql.org/docs/current/sql-createindex.html>

## 19. Test strategy and local acceptance matrix

Implementation follows RED/GREEN per bounded unit. Existing tests are updated only where the approved compatibility break changes the contract; no test is skipped, deleted, or weakened to manufacture a pass.

### 19.1 Strict model and safe HTTP tests

Prove:

- valid canonical TikTok and Shopify bodies;
- exact platform and UUID grammar;
- strict types and no coercion;
- metadata bounds, control-character rejection, duplicate-tag rejection, and 16 KiB cap;
- every old authority/path/URL/content field is rejected;
- old `platforms` bodies and multi-platform forms are rejected;
- invalid JSON and validation errors omit input, context, URLs, credentials, and raw values;
- validation fails before readiness, persistence, consume, or connector fakes are touched.

### 19.2 Permission tests

Prove both routes:

- allow `artifact:publish` and `all`;
- deny `artifact:accept` only;
- deny `provider:submit` only;
- deny malformed/unknown permission sets;
- bind tenant only from `AuthContext`;
- leave status/platform read routes unchanged.

### 19.3 Repository and migration tests

SQLite tests prove:

- fresh schema and existing-database compatibility columns;
- `prepared` creation and every legal transition;
- illegal and terminal transitions fail;
- tenant-bound compare-and-set behavior;
- safe JSON serialization and no secret/absolute-path storage;
- store failure typing;
- production mode cannot silently use SQLite.

Disposable PostgreSQL 18 tests prove:

- upgrade from `e8f1a2b3c4d5` to the W1-23 revision;
- required columns, types, nullability, and indexes;
- downgrade to `e8f1a2b3c4d5` and re-upgrade;
- fresh-init parity;
- legacy row preservation;
- repository lifecycle against real asyncpg;
- concurrent compare-and-set behavior;
- schema dump/restore verification sees the new column set.

No production database is contacted.

### 19.4 Service ordering and failure injection

Injected fakes record call order and prove:

- readiness precedes attempt creation;
- `prepared` precedes consume;
- consume precedes `acceptance_consumed` persistence;
- connector follows durable `acceptance_consumed` only;
- exactly one connector call occurs;
- terminal persistence follows the connector result;
- prepared-store failure leaves acceptance available;
- acceptance-store failure causes no connector call;
- consume-store failure after a possible CAS runs one read-only outcome inspection, never calls the connector, and forbids retry unless availability is positively proven;
- post-CAS response-projection failure and commit-acknowledgement loss cannot be misreported as `acceptance_consumed=false`;
- mark-after-consume failure causes no connector call and no restore;
- post-consume artifact-resolution failure becomes `failed`, causes no connector call, and forbids retry;
- explicit connector failure becomes `failed` and stable `502`;
- timeout, exception, malformed result, and missing success truth become `ambiguous` and stable `502`;
- final audit-store failure returns stable `500` and forbids retry;
- no failure path restores acceptance or schedules work.

### 19.5 Fast and Scenario integration

Use real W1-22 service/repository behavior with local exact-byte fixture files and an injected fake connector:

- one accepted Fast final video publishes through the canonical route;
- one accepted Scenario final video publishes through the deprecated adapter;
- server connector payload uses the accepted path and safe metadata only;
- a changed file fails integrity before connector work;
- cross-tenant acceptance is non-enumerable and cannot publish;
- consumed, expired, revoked, and rejected records cannot publish;
- `artifact:accept` reviewer and `provider:submit` generator keys cannot publish.

### 19.6 Concurrency

Run a bounded cohort of 20 concurrent publish requests with one tenant, one acceptance, one platform, and an instrumented fake connector. Required result:

- exactly one W1-22 consume winner;
- exactly one connector invocation;
- exactly one terminal connector-bearing attempt;
- 19 authorization losers;
- no acceptance restore;
- no automatic retry;
- no cross-tenant row access.

Repeat the authority portion against disposable PostgreSQL 18. SQLite remains local serialization evidence, not cross-process production proof.

### 19.7 OpenAPI and frontend tests

Prove:

- both request bodies are present, required, and share the strict schema;
- canonical and legacy success/error models match;
- legacy operation is deprecated;
- no HTTP consume endpoint exists;
- generated `web/src/types/api.generated.ts` matches local OpenAPI;
- `publishContent` and `publishVideo` make zero network calls without valid acceptance;
- `publishVideo` makes zero network calls for zero or multiple platforms;
- helpers never send client path/URL/human authority fields;
- one valid helper request sends one POST and one platform;
- current UI component tests remain green without inventing acceptance state.

### 19.8 Regression and full gates

Required final local gates include:

- focused W1-23 backend tests;
- focused W1-22 acceptance service/repository/router regression;
- current distribution guard, connector, metrics-source, auth, migration, backup/restore, route-governance, and OpenAPI tests;
- Ruff on changed Python plus final repository Ruff;
- full `make ci`;
- frontend Vitest run;
- frontend ESLint;
- frontend TypeScript `--noEmit`;
- `npm run check:api-types`;
- Next production build;
- `git diff --check`;
- changed-file secret-pattern scan without reading `.env` or credential files;
- independent read-only spec, security, concurrency, migration, and evidence-boundary review;
- resolution of every accepted Critical or Important finding.

No live connector, provider, SSH, deployment, production database, or public-site mutation is part of these gates.

## 20. Documentation and governance synchronization

After code and local acceptance are complete, synchronize:

- enterprise roadmap W1-23 status and remaining W1-24/W1-26 boundaries;
- backend route auth contract for `artifact:publish|all`;
- artifact acceptance lifecycle runbook with consumed-by-attempt behavior;
- API reference for canonical and deprecated route contracts;
- publish operations runbook with zero-retry and ambiguous-outcome handling;
- migration/rollback and disaster-recovery schema notes;
- OpenAPI generated types;
- SDD/local acceptance evidence report;
- project guide current status if the local state changes materially.

Documentation must preserve the exact local boundary:

- `production unchanged`;
- `provider_call=false`;
- `live_publish=false`;
- `database_write=false` for production;
- `completed_local` at most.

## 21. Rollout and rollback boundary

### Local implementation rollout

1. implement strict contracts and permission tests;
2. implement additive schema and specialized repository;
3. implement shared service and injected readiness/connector boundaries;
4. replace both route bodies with the shared strict adapter;
5. update frontend helpers and zero-network tests;
6. regenerate local OpenAPI TypeScript;
7. run disposable PostgreSQL 18 and full quality gates;
8. complete independent review and documentation synchronization;
9. classify W1-23 as `completed_local` only if every mandatory criterion passes.

### Application rollback

If W1-23 code must be rolled back in a later authorized environment:

1. stop publish mutation traffic;
2. establish and verify an external or route-level fail-closed block for both publish mutations before replacing W1-23 code;
3. keep both mutations disabled throughout rollback; never reopen traffic on the current legacy body-authority implementation;
4. roll the application back before changing schema only if that version cannot expose the unsafe publish routes; otherwise roll forward to a safe fix instead;
5. verify no W1-23 service instance can write new attempt states;
6. preserve `publish_logs` rows for audit;
7. downgrade the additive indexes and columns only under separate database authorization;
8. do not restore consumed acceptance records;
9. reconcile any `prepared` or `acceptance_consumed` attempt manually before considering future publish authorization;
10. re-enable publish traffic only on a version that enforces server-side acceptance consumption and single-platform authority.

Schema rollback is not equivalent to undoing an external post. TikTok/Shopify deletion or rollback requires platform-specific authorization and evidence under W1-26.

## 22. Completion criteria

W1-23 may be marked `completed_local` only when fresh evidence proves all of the following:

- both mutation routes require `artifact:publish|all`;
- caller human assertions, paths, URLs, tenant, reviewer, and attempt identity are rejected;
- one strict request authorizes one platform only;
- both routes share one service and one attempt repository;
- durable `prepared` precedes W1-22 consume;
- durable `acceptance_consumed` precedes the connector;
- exactly one concurrent consume winner causes exactly one connector call;
- when the process and store complete terminal handling, deterministic failure and ambiguous outcome are distinct and durable; crash/stale active rows remain explicitly unresolved rather than being mislabeled terminal;
- every post-consume failure is non-retryable and never restores acceptance;
- known mock/missing-credential state fails before consume;
- legacy `video_id` has no file or authority role;
- frontend helpers make zero POSTs without acceptance;
- PostgreSQL 18 migration/downgrade/fresh-init and SQLite parity pass;
- OpenAPI and generated TypeScript agree;
- focused/full backend and frontend gates pass;
- W1-22 regression passes;
- independent review has no unresolved Critical or Important finding;
- final evidence explicitly states the production and external-action boundaries.

## 23. Deferred work and honest evidence ceiling

After local W1-23 closure, these items remain real:

- immutable artifact snapshot or object-version binding to close post-consume TOCTOU;
- W1-24 complete missing-credential fail-closed behavior and explicit `simulated=true` truth;
- W1-24 correction of connector-internal timeout/exception paths that currently collapse ambiguous outcomes into `success=false`;
- W1-25 Shopify credential SSOT and strong receipt validation;
- W5 acceptance selection/history UI, human rubric, rights/source review, and all-scenario operator UX;
- W1-26 separately authorized sandbox or production publish, deletion/rollback, delivery acceptance, and active-post metrics;
- production migration lock assessment, backup, migration, permission assignment, deployment, and smoke;
- external-result reconciliation for ambiguous timeouts before any future retry design;
- natural-person/legal identity governance beyond credential principal identity.

W1-23 therefore closes the local publish-authorization wiring and single-attempt orchestration boundary only. It does not prove an enterprise all-scenario production publish/delivery loop.
