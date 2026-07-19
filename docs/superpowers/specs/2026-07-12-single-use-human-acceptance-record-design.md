---
title: Single-Use Human Acceptance Record Design
doc_type: architecture
module: artifact-acceptance
topic: single-use-human-acceptance-record
status: stable
created: 2026-07-12
updated: 2026-07-20
owner: self
source: human+ai
---

# Single-Use Human Acceptance Record Design

**Status:** Written from the user-approved Option A and final-publishable-artifact boundary on 2026-07-12; awaiting written-spec review before implementation planning.

**Roadmap scope:** W1-22 only. W1-23 publish consumption, W1-24/W1-25 connector truth, W5 human rubric/live acceptance, and a universal artifact registry remain separate work.

**Evidence boundary:** Local design, implementation, fixtures, disposable PostgreSQL 18 checks, tests, and builds may reach `L2-fixture-or-dry-run`. This specification does not authorize a production migration, deploy, provider call, publish, delivery, production write, commit, push, or PR.

## 1. Problem and required outcome

The current distribution routes trust request-body fields such as `source=human`, reviewer text, `delivery_accepted=true`, and `publish_allowed=true`. A caller that can reach the route can therefore self-assert that a human accepted an artifact. The existing `PendingReviewDecisionRecord` is an offline candidate-review document; it is intentionally non-persistent and cannot grant publish or delivery authority.

W1-22 must establish a server-owned authority record with these properties:

- tenant identity comes only from the authenticated `AuthContext`;
- reviewer identity is the authenticated credential principal, never request-body text;
- scenario and source job come from the durable submission ledger;
- the record binds one exact final `pending_review` artifact version by canonical path, SHA-256, and byte size;
- acceptance creation is idempotent across ambiguous HTTP responses;
- an accepted record can be consumed at most once through an atomic repository transition;
- rejected, expired, revoked, altered, missing, bounded, stub, quarantined, degraded, intermediate, or cross-tenant artifacts never grant publish authority;
- production fails closed when the PostgreSQL authority store or required schema is unavailable;
- W1-23 can consume the record later without accepting any body-supplied human assertion.

## 2. Scope

### 2.1 In scope

This batch covers final publishable video artifacts produced by canonical async Fast and S1-S5 submissions:

- Fast resource: `resource_type=fast`, durable `task_id`, final result `video_path`;
- Scenario resource: `resource_type=scenario`, durable `label`, final `assemble_final` video path;
- storage scope: `tenants/<tenant>/pending_review/...` below the configured `OUTPUT_DIR`;
- decisions: `accepted` or `rejected`;
- API: create, read, and revoke;
- internal repository/service interface: atomic single-use consume for the later W1-23 publish integration;
- PostgreSQL, SQLite development/test parity, readiness, backup/restore, OpenAPI, documentation, and tests.

The schema keeps `artifact_kind` extensible across `text`, `image`, `audio`, and `video`, but the W1-22 resolver mints authority only for final video artifacts already represented by the current Fast/S1-S5 runtime. Supporting other artifact kinds requires a later server-owned artifact registry or equivalent source projection and cannot be enabled by accepting arbitrary logical refs.

### 2.2 Explicit non-goals

W1-22 does not:

- change `/distribution/publish` or `/publish/{video_id}` to consume an acceptance ID; that is W1-23;
- call TikTok, Shopify, poyo, Seedance, an LLM, TTS, webhook, or any other external provider;
- promote or copy files into a public directory;
- mutate `publish_allowed` or `delivery_accepted` inside generation results or scenario state;
- create a universal artifact registry for toolbox, offline packets, uploads, text objects, or historical smoke manifests;
- let an intermediate keyframe, clip, audio track, thumbnail, script, prompt, render manifest, fixture, or mock result mint publish authority;
- add a new review UI; generated OpenAPI types are updated, while W5 owns human rubric and live acceptance UX;
- backfill an accepted record for existing artifacts or rewrite existing API-key permissions;
- prove that a credential principal corresponds to a named natural person. Production key issuance and reviewer-to-person governance remain an owner responsibility.

## 3. Security and authority invariants

The following invariants are mandatory:

1. `tenant_id`, `scenario`, reviewer identity, artifact digest, status, and consume metadata are server-owned fields.
2. The create body rejects `tenant_id`, `scenario`, `reviewer`, `reviewer_id`, `source`, `decision_source`, `artifact_sha256`, `artifact_size_bytes`, `status`, `publish_allowed`, `delivery_accepted`, `consumed_at`, and unknown fields.
3. The mutation requires `artifact:accept` or `all`. A key carrying only `provider:submit` receives `403` before artifact resolution or persistence.
4. The request's `source_resource_type` and `source_resource_id` must resolve through the current tenant's durable `idempotency_records` row.
5. Unknown and cross-tenant resources, files, and acceptance IDs use the same `404` projection.
6. An accepted record is valid only for the exact canonical artifact path and exact bytes hashed at review time.
7. The server stores only a SHA-256 hash of `Idempotency-Key`; raw action keys, API keys, provider credentials, and secret values are never stored, logged, or returned.
8. No HTTP route exposes the consume primitive. Only later server-side publish code may invoke it.
9. Losing store authority, path authority, source authority, or content integrity is not recoverable by trusting the request; the operation fails closed.
10. One accepted record authorizes one publish mutation attempt, not unlimited platforms, retries, or future artifact versions.
11. A later `rejected` decision for the same source/path atomically revokes any currently `available` acceptance before the rejection record is inserted; the old approval cannot remain usable.

## 4. Permission and reviewer identity

Add `artifact:accept` to `_RECOGNIZED_TENANT_PERMISSIONS`.

Authorization behavior:

- DB tenant key with `artifact:accept`: may create/read/revoke tenant acceptance records;
- DB tenant key with `all`: may create/read/revoke;
- DB tenant key with only `provider:submit`: denied;
- malformed, empty, mixed-known-and-unknown, or unrecognized permissions: normalize to no permissions as today;
- private env/test-bundle principals with `all`: remain usable for local hermetic tests and controlled operator workflows.

Persist reviewer identity as two server-derived fields:

- `reviewer_key_id = AuthContext.key_id`;
- `reviewer_key_type = AuthContext.key_type`.

If `key_id` is unexpectedly absent, acceptance mutation fails `503`/internal authority error rather than accepting a caller-provided identity. `review_notes` is human-entered context, not identity or authority.

## 5. Final artifact source projection

### 5.1 Durable source identity

The create request supplies only:

- `source_resource_type`: `fast` or `scenario`;
- `source_resource_id`: original Fast `task_id` or Scenario `label`;
- `artifact_path`: the canonical relative media path the reviewer inspected.

The service reads the tenant-bound durable submission record and derives `scenario`. A body-supplied scenario is invalid.

### 5.2 Fast eligibility

An accepted Fast artifact requires all of the following in the durable terminal result:

- submission `record_status=completed`;
- `scenario=fast` and `resource_type=fast`;
- `full_media_success=true`;
- `is_stub=false`;
- `artifact_disposition=pending_review`;
- result `video_path` resolves to the exact requested canonical path;
- the path is below `tenants/<tenant>/pending_review/fast_mode/<task_id>/`;
- the resolved file exists, is a regular file, and has a supported final video extension.

A rejected Fast decision still requires an exact final `video_path` and a tenant `pending_review` file, but it may bind a terminal failed/degraded source if that source persisted a final artifact. If there is no final artifact projection, no server acceptance record is created.

### 5.3 Scenario eligibility

Scenario terminal persistence adds an allowlisted source projection to the existing safe idempotency result snapshot:

- `final_artifact_path` from `assemble_final`, using `extract_assemble_paths()` for dict/list/tuple persistence shapes;
- `artifact_disposition` from the server-owned effective generation policy;
- `artifact_kind=video`;
- existing `pipeline_degraded`, lifecycle, success, and completion fields.

The terminal projector canonicalizes `final_artifact_path` below `OUTPUT_DIR` before writing the safe snapshot. It stores only the tenant-owned relative POSIX path. If the assemble output is missing, outside the output root, outside the authenticated tenant/disposition scope, or otherwise invalid, the projector omits the path and the resource cannot mint acceptance authority. It never stores a host absolute path in the acceptance source projection.

An accepted Scenario artifact requires:

- submission `record_status=completed`;
- `resource_type=scenario` and `scenario` in `s1`-`s5`;
- `pipeline_degraded` is not true;
- `artifact_disposition=pending_review`;
- a non-empty `final_artifact_path` that resolves to the exact requested canonical path;
- the path is below `tenants/<tenant>/pending_review/<label>/`;
- the resolved file exists, is regular, and has a supported final video extension.

A rejected Scenario decision may bind a terminal `completed` or `failed` resource when an exact final source projection exists. It never creates an `available` authority record.

### 5.4 Canonical file identity

Extract a shared artifact-path resolver from the existing media ownership behavior instead of copying weaker prefix checks. It must:

1. reject absolute URLs, schemes, query strings, fragments, control/null bytes, empty segments, `.`, `..`, and repeated decoding tricks;
2. normalize a server-produced absolute path under `OUTPUT_DIR` or a client-supplied canonical relative path into one relative POSIX path;
3. resolve symlinks and require the result to remain below `OUTPUT_DIR`;
4. reuse tenant ownership classification and return `404` for another tenant;
5. require the `pending_review` root and exact source-resource subdirectory;
6. require `.mp4` or `.webm` for the initial final-video contract;
7. stream the file through SHA-256 without loading it all into memory;
8. record the byte count from the same resolved file.

The stored identity is `(tenant_id, artifact_path, artifact_sha256, artifact_size_bytes)`. A later consume call re-resolves and re-hashes the file before attempting the database transition. A changed, missing, or moved file is not consumable.

## 6. Create request and fingerprint

### 6.1 Request model

`POST /acceptance-records` consumes:

```json
{
  "source_resource_type": "scenario",
  "source_resource_id": "s2_1783830000_abcdef12",
  "artifact_path": "tenants/momcozy-marketing/pending_review/s2_1783830000_abcdef12/assemble/final.mp4",
  "decision": "accepted",
  "review_notes": "Brand, product, rights, continuity, captions, and final render reviewed.",
  "expires_in_seconds": 3600
}
```

Validation is strict:

- `source_resource_type`: exact enum `fast|scenario`;
- `source_resource_id`: 1-128 characters and the existing safe resource-ID grammar;
- `artifact_path`: 1-1024 characters before canonical resolution;
- `decision`: exact enum `accepted|rejected`;
- `review_notes`: trimmed, 1-2000 characters;
- `expires_in_seconds`: strict integer, minimum 300, maximum 86400, default 3600;
- extra fields: forbidden.

The route parses raw JSON only after authentication, permission, and header validation, and projects validation errors to `type`, `loc`, and `msg`. It never returns Pydantic `input`, `ctx`, or URL fields.

### 6.2 Idempotent creation

`Idempotency-Key` is mandatory and uses the already approved 16-128 character grammar and duplicate-header rejection. The acceptance table stores only `creation_key_hash`.

Fingerprint version is `acceptance-create.v1`. The canonical request hash includes:

- fingerprint version;
- authenticated tenant ID;
- reviewer key ID and key type;
- validated request values, including decision, notes, and TTL;
- source resource type and ID;
- syntactically canonical artifact path.

The live file digest is stored in the record but is not needed to identify a same-action replay. Therefore a same-key replay can return the original record even if the file was later moved or changed; that record will still fail integrity validation at consume time.

Creation outcomes:

- first valid action: create one record and return `201` with `idempotent_replay=false`;
- same tenant/key/fingerprint: return the original current record and `200` with `idempotent_replay=true`;
- same tenant/key/different fingerprint or reviewer principal: `409 acceptance_payload_conflict`;
- different tenant using the same opaque key: independent namespace;
- a different key attempting to create a second `available` record for the same canonical path: `409 acceptance_already_available`. A changed digest does not bypass the active-path gate; the prior record must be revoked or expire before a newly reviewed version can become available.

## 7. Durable schema

Add `acceptance_records` to Alembic, fresh PostgreSQL init SQL, SQLite init, required-table health, and logical backup/restore/verify manifests.

Required columns:

| Column | Contract |
|---|---|
| `id` | Opaque UUID/text `acceptance_id`; also the single-use nonce |
| `tenant_id` | Authenticated owner |
| `creation_key_hash` | SHA-256 of create `Idempotency-Key` |
| `fingerprint_version` | `acceptance-create.v1` |
| `request_hash` | Canonical create-request SHA-256 |
| `source_resource_type` | `fast` or `scenario` |
| `source_resource_id` | Original task ID or label |
| `scenario` | Server-derived `fast` or `s1`-`s5` |
| `artifact_path` | Canonical relative POSIX path |
| `artifact_sha256` | Exact reviewed file digest |
| `artifact_size_bytes` | Exact reviewed byte count |
| `artifact_kind` | Schema enum `text|image|audio|video`; W1-22 writes `video` |
| `decision` | `accepted` or `rejected` |
| `record_status` | `available`, `rejected`, `consumed`, `expired`, or `revoked` |
| `reviewer_key_id` | Authenticated credential ID |
| `reviewer_key_type` | Authenticated credential type |
| `review_notes` | Bounded human review context |
| `expires_at` | Database-time authority expiry |
| `consumed_at` | Single-use transition time |
| `consumed_by_operation` | Future server operation, initially expected `distribution.publish` |
| `consumed_by_resource_id` | Future publish-attempt/resource identity |
| `revoked_at` | Revocation time |
| `revoked_by_key_id` | Authenticated revoker credential ID |
| `revoked_by_record_id` | Rejection record that caused automatic revocation; null for explicit revoke |
| `created_at`, `updated_at` | Audit timestamps |

Required constraints and indexes:

- primary key `id`;
- unique `(tenant_id, creation_key_hash)`;
- partial unique `(tenant_id, artifact_path)` where `record_status='available'`;
- indexes on `(tenant_id, source_resource_type, source_resource_id)`, `(tenant_id, record_status)`, and `expires_at` for available rows;
- checks for scenario, resource type, artifact kind, decision, and record status;
- `artifact_size_bytes > 0`;
- `decision=accepted` permits `available|consumed|expired|revoked` only;
- `decision=rejected` requires `record_status=rejected`;
- `record_status=consumed` requires non-null consume time, operation, and resource ID; all other statuses keep those fields null;
- `record_status=revoked` requires revocation time and revoker; all non-revoked statuses keep those fields null;
- `revoked_by_record_id`, when present, identifies a same-tenant `rejected` record for the same source/path;
- `expires_at > created_at`.

The partial unique index is supported by both PostgreSQL 18 and SQLite. It prevents multiple simultaneously usable approvals while retaining immutable historical consumed/rejected rows.

## 8. Repository contract and concurrency

Create a dedicated `AcceptanceRecordRepository`; do not extend the generic read-then-create `BaseRepository`.

Required operations:

```python
async def create_or_replay(...) -> CreateAcceptanceResult: ...
async def get_by_id(*, tenant_id: str, acceptance_id: str) -> dict[str, object] | None: ...
async def revoke(*, tenant_id: str, acceptance_id: str, reviewer_key_id: str) -> dict[str, object] | None: ...
async def consume(*, tenant_id: str, acceptance_id: str, artifact_path: str,
                  artifact_sha256: str, consumer_operation: str,
                  consumer_resource_id: str) -> dict[str, object] | None: ...
async def reconcile_expired(*, tenant_id: str, acceptance_id: str | None = None,
                            artifact_path: str | None = None) -> int: ...
```

### 8.1 PostgreSQL

- creation uses a transaction, database time, unique constraints, and `INSERT ... ON CONFLICT DO NOTHING RETURNING *`;
- every new decision first locks the tenant-owned source `idempotency_records` row with `SELECT ... FOR UPDATE`; accepted and rejected decisions for one Fast task/Scenario label therefore commit in a deterministic serial order;
- before inserting an accepted record, expired `available` rows for the same tenant/path are changed to `expired`;
- before inserting a rejected record, any `available` row for the same tenant/path is changed to `revoked` with the rejecting reviewer, timestamp, and new rejection-record ID; the rejection row is then inserted in the same transaction;
- a create-key conflict reads the committed row and compares fingerprint version/hash;
- an active-artifact partial-index conflict maps to `acceptance_already_available`;
- consume uses one conditional `UPDATE ... WHERE record_status='available' AND expires_at > NOW() AND artifact_path/artifact_sha256 match RETURNING *`;
- revoke uses compare-and-set from `available` to `revoked`;
- late or duplicate callers cannot move `consumed`, `expired`, `revoked`, or `rejected` back to `available`.

The last serialized human decision is authoritative for future actions. If acceptance commits and rejection follows, rejection revokes it. If rejection commits and a later authenticated acceptance follows after re-validating current bytes, the newer acceptance may become `available`. Both records remain immutable audit history.

### 8.2 SQLite

Development and hermetic tests mirror the same behavior under the existing SQLite lock and `BEGIN IMMEDIATE`. The schema includes the same unique and partial unique indexes. An `asyncio.Lock` or in-memory dictionary is not authority.

### 8.3 Production fail-closed behavior

In `prod|production`, repository construction requires a verified PostgreSQL pool and `acceptance_records` table. It never falls back to SQLite, filesystem JSON, or memory. Store failure maps to `503 acceptance_store_unavailable` before a record or authority transition is claimed.

## 9. Service contract

`ArtifactAcceptanceService` owns validation and projection:

1. validate header and strict request without echoing inputs;
2. derive tenant and reviewer from `AuthContext`;
3. compute create fingerprint and check same-key replay before live file access;
4. resolve the tenant-owned submission and derive scenario/source eligibility;
5. resolve the exact final artifact path and verify source/path equality;
6. compute file SHA-256 and byte size;
7. create or replay the durable record;
8. return a safe response projection.

The service never calls a provider or publish connector and never changes the generation state.

Safe response example:

```json
{
  "acceptance_id": "a0c907c0-9f5d-44e4-bad8-cb0b8af30e7e",
  "tenant_id": "momcozy-marketing",
  "source_resource_type": "scenario",
  "source_resource_id": "s2_1783830000_abcdef12",
  "scenario": "s2",
  "artifact": {
    "path": "tenants/momcozy-marketing/pending_review/s2_1783830000_abcdef12/assemble/final.mp4",
    "sha256": "64-lowercase-hex-characters",
    "size_bytes": 123456,
    "kind": "video"
  },
  "decision": "accepted",
  "status": "available",
  "reviewer": {
    "key_id": "authenticated-key-id",
    "key_type": "tenant"
  },
  "review_notes": "Brand, product, rights, continuity, captions, and final render reviewed.",
  "expires_at": "2026-07-12T12:00:00Z",
  "consumed_at": null,
  "revoked_at": null,
  "idempotent_replay": false,
  "created_at": "2026-07-12T11:00:00Z",
  "updated_at": "2026-07-12T11:00:00Z"
}
```

The artifact digest is not a secret and is returned so an operator can audit exact content identity. No raw action key, API key, provider credential, owner instance, database error, or full source-state payload is returned.

## 10. HTTP API

### 10.1 Create

`POST /acceptance-records`

- dependencies: authentication plus `artifact:accept` permission;
- required header: `Idempotency-Key`;
- body: Section 6.1;
- `201`: new record;
- `200`: same-action replay;
- no automatic POST retry.

### 10.2 Read

`GET /acceptance-records/{acceptance_id}`

- dependencies: authentication plus `artifact:accept` permission;
- tenant-bound lookup;
- lazily reconciles `available` records whose database expiry has passed;
- returns current safe projection;
- unknown/cross-tenant ID: `404 acceptance_not_found`.

### 10.3 Revoke

`POST /acceptance-records/{acceptance_id}/revoke`

- dependencies: authentication plus `artifact:accept` permission;
- `available -> revoked` records revoker and database time;
- repeating revoke by the same tenant returns the current revoked record without creating a new transition;
- consumed, expired, or rejected records return `409 acceptance_not_revocable`;
- cross-tenant/unknown returns `404`.

### 10.4 Internal consume boundary

There is no `/consume` HTTP endpoint in W1-22.

The service exposes `consume_for_publish(...)` for W1-23. It:

1. tenant-loads the acceptance ID;
2. requires `decision=accepted` and current `status=available`;
3. re-resolves the stored path and re-hashes the file;
4. compares current path/digest/size to the reviewed identity;
5. atomically changes `available -> consumed` with a future publish operation and attempt ID;
6. permits exactly one concurrent winner.

W1-23 must invoke this before the external publish mutation. A connector failure does not automatically restore `available`; another live publish attempt requires a new human acceptance record. This preserves single-attempt authority and the existing zero-retry mutation rule.

## 11. Stable error contract

| HTTP | Code | Condition |
|---|---|---|
| `400` | `acceptance_key_required` | Create header missing |
| `400` | `acceptance_key_invalid` | Header malformed or duplicated |
| `403` | `Insufficient permission` | Authenticated principal lacks `artifact:accept|all` |
| `404` | `acceptance_not_found` | Unknown or cross-tenant acceptance/resource/artifact |
| `409` | `acceptance_payload_conflict` | Same tenant/key, different fingerprint or reviewer |
| `409` | `acceptance_source_not_terminal` | Source is still reserved/initializing/queued/running |
| `409` | `acceptance_source_not_eligible` | Recovery-required, bounded, stub, quarantined, degraded accepted source, or missing final projection |
| `409` | `acceptance_artifact_mismatch` | Requested path differs from server final artifact |
| `409` | `acceptance_already_available` | Another usable approval exists for the same canonical path |
| `409` | `acceptance_not_revocable` | Record is consumed, expired, or rejected |
| `422` | safe validation projection | Strict request invalid; no input echo |
| `503` | `acceptance_store_unavailable` | Required durable authority store unavailable |

Internal consume returns stable typed failures for `not_found`, `not_available`, `expired`, and `artifact_integrity_mismatch`. W1-23 will decide their HTTP projection without changing repository semantics.

## 12. Expiry, revocation, and restart truth

- accepted records start `available`; rejected records start and remain `rejected`;
- creating a rejected record atomically revokes an earlier available record for the same tenant/source/path; a rejection never grants consume authority;
- expiry uses database time, not application-host time;
- default validity is 3600 seconds, allowed range 300-86400 seconds;
- GET, create-for-same-artifact, revoke, and consume lazily reconcile expired available rows through compare-and-set;
- process restart does not alter authority because all state is durable;
- a deleted or modified artifact leaves the historical record intact but makes consume fail integrity validation;
- a consumed record is never reusable, revocable, or reset to available;
- an expired or revoked record remains immutable history; a fresh human action with a new idempotency key may create a new record after re-validating current bytes;
- physical retention/deletion of historical records is out of scope and must not reopen a consumed acceptance ID.

## 13. Database, backup, and readiness integration

The change is additive and advances the Alembic head from `d5e6f7a8b9c0` to one new revision.

Update together:

- Alembic upgrade/downgrade;
- `src/storage/migrations/001_init.sql`;
- SQLite table/index initialization;
- `_REQUIRED_TABLES` readiness list;
- `scripts/pg_dump_logical.py`;
- `scripts/pg_restore_logical.py`;
- `scripts/verify_restored_database.py`;
- backup/restore/migration governance tests.

After the migration, the current logical backup contract contains 14 tables. Historical 12- and 13-table evidence remains valid only for its recorded date and schema head.

Deploying application code without the migration makes production readiness fail rather than silently disabling acceptance authority. Downgrade requires rolling back application code and then dropping the additive table. No production migration or deploy is part of this local implementation batch.

## 14. OpenAPI and documentation

Mount a dedicated domain router in `src/api.py`. Define Pydantic models so local OpenAPI describes the create/read/revoke contract and required `Idempotency-Key` header.

Regenerate `web/src/types/api.generated.ts` only through the existing local generator. W1-22 does not add frontend components or persist acceptance state in the browser.

Synchronize:

- `docs/reference/api-endpoints.md`;
- backend auth/permission contract and runbook;
- a new acceptance lifecycle/recovery runbook;
- the all-scenario roadmap status;
- the tracked roadmap and acceptance lifecycle runbook;
- `AGENTS.md` only when local closure is verified and the durable project fact is stable.

## 15. TDD and verification strategy

Implementation follows strict RED/GREEN cycles.

### 15.1 Pure contract tests

- strict request types, bounds, extra-field rejection, and safe 422 projection;
- creation fingerprint order/default/type behavior;
- reviewer principal included in fingerprint;
- credential and raw-key exclusion;
- canonical path normalization and traversal/scheme/encoding rejection;
- streaming digest and exact byte count.

### 15.2 Repository tests

PostgreSQL and SQLite must cover:

- create owner/replay/conflict;
- same opaque key across tenants remains isolated;
- 20 concurrent same-key creates yield one owner and nineteen replays;
- concurrent different keys for the same artifact yield one `available` record;
- concurrent accepted/rejected decisions serialize on the source row and leave the last decision authoritative, with rejection revocation linkage preserved;
- accepted/rejected status invariants;
- database-time expiry reconciliation;
- revoke idempotency and terminal-state protection;
- concurrent consume yields one winner and all others fail closed;
- digest/path mismatch cannot consume;
- repository reconstruction after close/reopen preserves truth;
- production store unavailability never falls back.

### 15.3 Source and service tests

Parameterize Fast and S1-S5 to prove:

- tenant/scenario/reviewer derive from server authority;
- exact final path succeeds for eligible fixture resources;
- bounded/no-media, Fast stub, quarantine, degraded accepted source, intermediate path, absent assembly, missing file, symlink escape, cross-tenant path, and altered bytes fail before insert;
- rejected final artifacts create `rejected`, never `available`;
- same-key replay needs no live file access and returns original current status;
- no provider/client/translator/connector boundary is called.

### 15.4 HTTP tests

- missing/invalid/duplicate action key;
- `provider:submit`-only key denied;
- create `201`, replay `200`, conflict `409`;
- tenant-bound read/revoke and cross-tenant `404`;
- no public consume route;
- safe errors contain no request input, credentials, raw action key, absolute host path, or raw exception;
- response wrapper and OpenAPI contract remain valid.

### 15.5 Integration and full gates

- disposable PostgreSQL 18 upgrade from `d5e6f7a8b9c0`, constraints/index inspection, concurrent consume, downgrade, and fresh-init parity;
- required-table health and 14-table backup/restore/row-parity checks;
- focused backend tests and Ruff;
- full `make ci`;
- frontend Vitest, ESLint, TypeScript, OpenAPI drift guard, and Next build because generated API types change;
- `git diff --check` and changed/untracked secret-pattern scan;
- independent security/spec review with all accepted Critical/Important findings resolved.

All tests remain hermetic: `provider_call=false`, no production connection, no publish, no delivery, and no `.env` read.

## 16. Acceptance criteria

W1-22 may be marked `completed_local` only when all of the following are freshly evidenced:

- one authenticated reviewer action creates one durable tenant-bound record;
- the same action safely replays and a changed action conflicts without a second record;
- tenant, scenario, reviewer, final artifact path, digest, size, decision, expiry, and nonce are server-owned and durable;
- only exact eligible Fast/S1-S5 final `pending_review` videos can become `available`;
- bounded, stub, degraded accepted, quarantined, intermediate, missing, altered, and cross-tenant artifacts cannot grant authority;
- exactly one concurrent consume succeeds and no terminal record returns to `available`;
- a later rejection cannot coexist with an older usable approval for the same source/path;
- production store absence fails before authority creation or transition;
- PostgreSQL 18 migration/fresh-init/downgrade and SQLite parity pass;
- required-table readiness and 14-table backup/restore contracts pass;
- OpenAPI types, docs, focused/full quality gates, secret scan, and independent review pass;
- the final report states `production unchanged`, `provider_call=false`, and that publish still trusts the old body until W1-23 is separately implemented.

## 17. Deferred work and honest evidence ceiling

After W1-22 local closure:

- W1-23 must remove request-body human assertions from publish routes and consume only a server-side acceptance ID;
- W1-24/W1-25 must enforce real connector credential/receipt truth and simulated-result semantics;
- W5 must add rubric/source/rights review records, operator UX, and separately authorized live scenario acceptance;
- a future artifact registry is required before text, image, audio, toolbox, or arbitrary logical `artifact://` refs can receive equivalent server authority;
- reviewer key identity is auditable credential identity, not proof of a natural person's legal identity;
- no production acceptance exists until migration, deployment, permission assignment, an actual human review, publish integration, and separately authorized production evidence occur.

This specification therefore closes the local W1-22 authority primitive only. It does not claim enterprise full-chain publishing, delivery, or all-scenario production acceptance.

## 18. Implementation references

- PostgreSQL 18 partial indexes: <https://www.postgresql.org/docs/18/indexes-partial.html>
- PostgreSQL 18 `UPDATE ... RETURNING`: <https://www.postgresql.org/docs/18/sql-update.html>
- PostgreSQL 18 `SELECT ... FOR UPDATE`: <https://www.postgresql.org/docs/18/sql-select.html#SQL-FOR-UPDATE-SHARE>
- SQLite partial indexes: <https://sqlite.org/partialindex.html>
- Parent closure design: `docs/superpowers/specs/2026-07-11-enterprise-ai-content-all-scenarios-closure-design.md`
- Current roadmap: `docs/workflows/enterprise-ai-content-all-scenarios-roadmap-20260711.md`
- Durable submit foundation: `docs/superpowers/specs/2026-07-12-tenant-scoped-submit-idempotency-design.md`
