---
title: Tenant-Scoped Submit Idempotency Design
doc_type: architecture
module: submission
topic: tenant-scoped-submit-idempotency
status: stable
created: 2026-07-12
updated: 2026-07-20
owner: self
source: human+ai
---

# Tenant-Scoped Submit Idempotency Design

**Status:** Written from the user-approved Option A on 2026-07-12; awaiting written-spec review before implementation planning.

**Roadmap scope:** W1-13, W1-15, and W1-16.

**Evidence boundary:** Local design, implementation, fixtures, disposable-database checks, tests, and builds may reach `L2-fixture-or-dry-run`. This specification does not authorize a production migration, deploy, provider call, publish, delivery, or production write.

## 1. Problem and outcome

The canonical browser generation paths currently submit Fast Mode and S1-S5 through asynchronous POST endpoints, but the submit action has no durable idempotency claim. A lost response leaves the browser without the returned `task_id` or `label`; retrying with a new request can create a second task and repeat paid work.

The required outcome is:

- one explicit user action has one stable `Idempotency-Key`;
- tenant identity always comes from the authenticated server context;
- the first request atomically claims the key before translation, state initialization, task creation, or any provider-capable await;
- the same tenant, key, and canonical payload always resolve to the original job;
- the same tenant and key with a different canonical payload return `409` without side effects;
- the mapping and truthful job status survive repository and process restart;
- the browser can recover an ambiguous response through tenant-bound GET readback without sending a blind second POST;
- raw idempotency keys are never persisted server-side or logged; the browser may persist only the minimal pending key required for recovery, and provider credentials are never persisted by this feature.

## 2. Scope

### 2.1 Canonical async endpoints

This batch makes `Idempotency-Key` mandatory on:

- `POST /fast/submit`;
- `POST /scenario/{scenario}/submit`, where `scenario` is `s1`, `s2`, `s3`, `s4`, or `s5`.

It adds:

- `GET /submissions/idempotency`, authenticated and tenant-bound, with the key supplied through the same header.

The existing status endpoints remain:

- `GET /fast/status/{task_id}`;
- `GET /scenario/{scenario}/status/{label}`.

### 2.2 Explicit non-goals

This batch does not:

- make `/fast/generate`, `/scenario/s1` through `/scenario/s5`, `/scenario/s1/start`, `/pipeline/start`, gate mutation, regenerate, publish, or delivery endpoints replayable;
- relax `provider_max_retries=0` or introduce an automatic mutation retry;
- implement a provider-recognized attempt ledger, cost ledger, or budget reservation;
- automatically resume paid work after a worker/process restart;
- persist request-scoped provider credentials for later replay;
- execute a production migration, deploy, provider generation, publish, or delivery action.

Blocking and legacy mutation endpoints remain zero-retry and explicitly non-replayable. Full worker resume is W6-02, not W1-16.

## 3. Decisions

### 3.1 Required header and compatibility

The two canonical async POST surfaces fail closed when `Idempotency-Key` is absent or invalid. This is an intentional compatibility break approved for Option A. Repository-owned frontend calls, tests, production specs, API references, CORS, and generated OpenAPI types must be updated in the same change set.

The header value is:

- case-sensitive and opaque;
- 16 to 128 visible ASCII characters;
- matched by `^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$`;
- rejected when empty, duplicated, oversized, or containing whitespace/control characters.

The raw value is never returned, logged, stored by the server, placed in a URL, or added to an error message. The browser's minimal pending-submission record described in Section 9 is the only permitted raw-key persistence. Request-body `idempotency_key` remains forbidden and continues to return `422` as an unsupported client authority assertion.

### 3.2 Tenant-global key namespace

Uniqueness is enforced on `(tenant_id, key_hash)`, not on `(tenant_id, operation, key_hash)`.

Operation and scenario are part of the request fingerprint. Reusing one key for Fast and S1, or for two different scenarios, therefore produces `409`. This prevents accidental cross-entry duplicate billing while still allowing two different tenants to use the same opaque key independently.

### 3.3 No automatic key reuse

The first implementation does not automatically expire or delete idempotency records. Physical retention can be added only with an explicit tombstone policy that does not reopen a previously used key for paid execution. This avoids an expiry-driven duplicate-submission window.

## 4. HTTP contract

### 4.1 Submit success and replay

The initial submit and a same-payload replay both preserve the current HTTP `200` status for compatibility. Core response fields remain unchanged, with one additive boolean:

Fast Mode:

```json
{
  "task_id": "fast_...",
  "status": "queued",
  "started_at_unix": 1783830000,
  "idempotent_replay": false
}
```

Scenario:

```json
{
  "label": "s1_...",
  "status": "queued",
  "trace_id": "...",
  "idempotent_replay": false
}
```

On replay, the original `task_id` or `label`, timestamp, and core response projection are returned with `idempotent_replay=true`. Dynamic response-wrapper `_meta` fields are generated per HTTP response and are not part of the stored projection.

The common successful path returns `status="queued"`. A concurrent replay that arrives while the owner is still preparing the job returns the same resource with the truthful current status (`reserved` or `initializing`); a replay after an abandoned lease returns `recovery_required`. The API never reports `queued` for a record that did not reach the queue. Frontend response types must accept these submission states and proceed through readback/status polling rather than treating them as a second job.

### 4.2 Deterministic errors

The API uses stable detail codes:

| HTTP | Code | Meaning |
|---|---|---|
| `400` | `idempotency_key_required` | Required header is missing |
| `400` | `idempotency_key_invalid` | Header format or multiplicity is invalid |
| `409` | `idempotency_payload_conflict` | Tenant/key already belongs to a different operation, scenario, or canonical payload |
| `404` | `submission_not_found` | Unknown key or another tenant's key |
| `503` | `idempotency_store_unavailable` | The required durable store is unavailable before side effects |

A conflict never changes the original record and never calls translation, state initialization, task creation, or a provider boundary.

### 4.3 Readback

`GET /submissions/idempotency` accepts `Idempotency-Key` in the header and returns:

```json
{
  "resource_type": "scenario",
  "resource_id": "s1_...",
  "scenario": "s1",
  "status": "running",
  "submit_response": {
    "label": "s1_...",
    "status": "queued",
    "trace_id": "..."
  },
  "created_at": "2026-07-12T00:00:00Z",
  "updated_at": "2026-07-12T00:00:04Z"
}
```

Readback requires authentication but not a second `provider:submit` authorization decision because it is a read of an already claimed tenant resource. Unknown and cross-tenant lookups both return the same `404` projection.

## 5. Durable submission ledger

### 5.1 Table

Add `idempotency_records` to Alembic, fresh PostgreSQL init SQL, SQLite init, and the required-table health contract.

Required columns:

| Column | Purpose |
|---|---|
| `id` | Stable internal record UUID/text ID |
| `tenant_id` | Authenticated owner |
| `key_hash` | SHA-256 digest of the raw header |
| `fingerprint_version` | Canonicalization contract, initially `submit-fingerprint.v1` |
| `request_hash` | SHA-256 digest of the canonical request envelope |
| `operation` | `fast.submit` or `scenario.submit` |
| `scenario` | `fast` or `s1`-`s5` |
| `resource_type` | `fast` or `scenario` |
| `resource_id` | Original `task_id` or `label` |
| `record_status` | Submission lifecycle state |
| `stage` | Safe current Fast/pipeline stage projection |
| `effective_policy_version` | Server policy version used by the job |
| `response_status` | Stored core submit HTTP status |
| `response_body` | Stored non-secret submit response projection, updated to the truthful submission status |
| `result_snapshot` | Allowlisted tenant-owned terminal Fast result or safe scenario projection |
| `safe_error_code` | Stable sanitized failure code, never a raw exception/secret |
| `owner_instance_id` | Runtime instance holding the current lease |
| `lease_expires_at` | Deadline used to identify an abandoned nonterminal owner |
| `created_at`, `updated_at`, `completed_at` | Audit timestamps |

Required constraints:

- unique `(tenant_id, key_hash)`;
- unique `(tenant_id, resource_type, resource_id)`;
- checks for allowed `resource_type`, `scenario`, and lifecycle states;
- non-null hashes, operation, resource identity, response projection, and timestamps.

No canonical request-payload copy or credential is stored. `result_snapshot` is a separate allowlisted tenant-owned result projection needed for status/result recovery; it may contain generated artifact references and lifecycle fields already returned by the API, but it must omit authentication/provider keys, raw exception text, and fields not required by the recovery UI.

### 5.2 Canonical request fingerprint

Fingerprint construction is server-owned:

1. Authenticate and obtain `AuthContext.tenant_id`.
2. Validate the scenario/Fast request with its Pydantic model.
3. Resolve `EffectiveGenerationPolicy` from authenticated authority.
4. Serialize the validated model with defaults included and `None` represented consistently.
5. Remove `api_keys` and every credential-bearing field from the fingerprint input.
6. Build an envelope containing fingerprint version, operation, scenario, normalized business payload, and effective policy.
7. Encode JSON with sorted object keys, compact separators, UTF-8, `allow_nan=false`, and list order preserved.
8. Compute SHA-256.

Consequences:

- omitted defaults and explicit defaults have the same hash;
- object key order does not matter;
- list order remains meaningful;
- booleans and integers remain distinct JSON values;
- changing only request-scoped provider credentials does not create a new business payload and does not expose credentials;
- operation, scenario, policy, or normalized business-input changes conflict under the same key.

Changing credentials after the original job definitively fails does not rerun that job under the same key. The failed original resource is replayed; a corrected credential attempt is a new explicit user action and therefore uses a new key.

## 6. Atomic claim repository

Create a dedicated repository rather than extending `BaseRepository` read-then-create behavior.

The repository exposes bounded operations:

- `claim(...) -> owner | replay | conflict`;
- `get_by_key_hash(tenant_id, key_hash)`;
- `get_by_resource(tenant_id, resource_type, resource_id)`;
- `transition(expected_statuses, new_status, safe_projection)` using compare-and-set;
- `reconcile_expired_lease(...)` using compare-and-set.

### 6.1 PostgreSQL

The claim uses the database unique constraint:

```sql
INSERT INTO idempotency_records (...)
VALUES (...)
ON CONFLICT (tenant_id, key_hash) DO NOTHING
RETURNING *;
```

If a row is returned, the caller is the sole owner. Otherwise, the repository reads the committed conflicting row and compares fingerprint version, request hash, operation, and scenario. An exact match is replay; any difference is conflict.

All lifecycle writes are compare-and-set updates so a late callback cannot move a terminal or `recovery_required` record back to `running`.

### 6.2 SQLite

Development and hermetic tests use the persistent SQLite database:

- acquire the existing SQLite lock;
- execute `BEGIN IMMEDIATE`;
- `INSERT OR IGNORE` under the same unique constraint;
- read and compare the row before commit;
- commit or roll back as one transaction.

An in-process `asyncio.Lock` is not the authority because it cannot protect multiple workers or restarts.

### 6.3 Production fail-closed rule

Production requires a healthy PostgreSQL pool and the `idempotency_records` table. It must not silently fall back to memory, JSON, filesystem state, or SQLite for generation submit. If the durable store is missing or unavailable, submit returns `503` before translation, `_inject_api_keys`, state initialization, task creation, or provider-capable work.

SQLite remains valid for development and tests only.

## 7. Endpoint execution order

Both async POST paths follow this order:

1. Authenticate and bind tenant context.
2. Validate the header.
3. Validate the request model and resolve effective policy.
4. Compute the secret-free canonical request hash.
5. Preallocate the original `task_id` or `label` and core submit response.
6. Atomically claim the durable record.
7. On replay, return the stored job projection immediately without injecting provider keys or invoking downstream work.
8. On conflict, return `409` without downstream work.
9. For the owner only, transition to `initializing`.
10. Start the independent lease heartbeat before translation or other provider-capable work.
11. Inject request-scoped provider keys and continue translation/state/task initialization.
12. Register the background execution, transition to `queued/running`, and maintain its lease.
13. Persist a terminal result or sanitized failure projection.

The claim must occur before S1/S3 catalog translation because that translation may call an LLM.

The initial claim stores a truthful `reserved` response projection. The owner updates it to `initializing` and then `queued` before returning the normal submit response. Concurrent callers read the current stored projection; they never manufacture `queued` locally.

### 7.1 Fast Mode

The in-memory Fast registry is reduced to live `asyncio.Task` handles. The ledger becomes the tenant-bound source of job identity, stage, safe error, and terminal result.

- `register_fast_task` accepts a preallocated `task_id` and record identity;
- stage callbacks update the ledger and lease;
- completion/failure callbacks persist the terminal snapshot using compare-and-set;
- `/fast/status/{task_id}` reads durable ownership/status and may enrich it from a live local handle;
- restart after terminal completion still returns the stored result;
- restart during nonterminal execution returns `recovery_required` after lease reconciliation rather than `404` or a duplicate submit.

### 7.2 Scenario S1-S5

The submission record owns the idempotency mapping while `PipelineStateManager` remains the full scenario-state authority.

- the preallocated label is passed to `StepRunner.init_state`;
- translation and state initialization happen only for the claim owner;
- the background wrapper maintains the submission lease/status;
- terminal scenario state is projected back to the ledger;
- readback may reconcile a stale ledger from an already terminal tenant-owned pipeline state;
- a lost nonterminal owner becomes `recovery_required`; it is not automatically resumed in this batch.

## 8. Crash and restart semantics

Lifecycle:

`reserved -> initializing -> queued -> running -> completed | failed | recovery_required`

Rules:

- `reserved` is persisted before side effects and already contains the original resource identity and submit projection;
- every nonterminal owner has `owner_instance_id` and a renewable lease;
- the default lease is 120 seconds, and every owner starts an independent heartbeat task immediately after claim and before translation/provider-capable work;
- the heartbeat renews every 30 seconds using database time, not application-host time, and uses compare-and-set on tenant, record ID, owner instance, and an allowed nonterminal status;
- heartbeat failure does not authorize replay: it is surfaced as an execution-control failure, the main work is stopped when safely possible, and the record becomes `recovery_required` through compare-and-set;
- a lease-expired nonterminal record is compare-and-set to `recovery_required`;
- readback/status performs lazy expired-lease reconciliation, and a periodic reconciler may perform the same compare-and-set; startup never blindly marks unexpired work owned by another instance;
- same-key replay always returns the original resource, including in `reserved`, `running`, or `recovery_required` state;
- no nonterminal crash state is interpreted as permission to send another provider mutation;
- a terminal result remains terminal under late callbacks;
- terminal completion/failure first performs the terminal compare-and-set and then stops the heartbeat; a late heartbeat cannot update a terminal row;
- graceful shutdown first compare-and-sets owned nonterminal records to `recovery_required`, then stops their heartbeat tasks, and finally cancels live work handles; an ungraceful crash is detected after lease expiry;
- lease tests inject database time and do not sleep;
- full automatic continuation is impossible without persisted provider credentials/attempt authority and is intentionally deferred to W6-02.

This satisfies W1-16 by preserving original-job identity and preventing duplicate execution across timeout and restart. It does not claim worker-resume completion.

## 9. Frontend recovery contract

### 9.1 Persisted pending submission

Upgrade pipeline-store persistence and introduce a minimal record:

```ts
type PendingSubmission = {
  kind: "scenario" | "fast";
  scenario?: "s1" | "s2" | "s3" | "s4" | "s5";
  idempotencyKey: string;
  createdAt: number;
  phase: "submitting" | "recovering" | "bound" | "unknown";
  resourceId?: string;
};
```

The browser persists this record before POST. It never persists the generation payload, provider API keys, authentication key, or model secrets.

One explicit Start/Generate action creates one key with `crypto.randomUUID()`. Every readback or user-directed retry for that action reuses the same key. A new key is allowed only for a new explicit action or after the user explicitly abandons an unknown/conflicting submission.

### 9.2 Ambiguous response state machine

Ambiguous outcomes include network failure, client timeout, caller abort after dispatch, and HTTP `500`, `502`, `503`, or `504` where the server may have accepted the mutation. A structured `503` with code `idempotency_store_unavailable` is definitive because this contract guarantees it occurs before claim or downstream work; an unstructured proxy/network `503` remains ambiguous.

The browser:

1. changes the UI to “confirming whether the job was created”;
2. performs bounded read-only lookups with the original key at approximately 0, 1, 2, and 5 seconds;
3. keeps polling idempotency readback while the record is `reserved` or `initializing`, because the Scenario state or Fast task handle may not exist yet;
4. binds and resumes the original Scenario/Fast resource polling only after readback reports `queued`, `running`, or a terminal state;
5. renders `recovery_required` directly from readback without calling a resource-status endpoint that may not exist;
6. keeps the pending record and shows a truthful unknown state after bounded lookup exhaustion;
7. offers “continue checking” without a POST;
8. requires confirmation before “abandon and start a new submission” creates a new key.

The helper never automatically sends a second mutation POST. `apiFetch` retains zero mutation retries. Reload hydration performs only readback/status GETs until a resource is bound.

### 9.3 Shared frontend implementation

A focused `idempotentSubmission` helper owns key generation, persistence transitions, ambiguous-error classification, bounded readback, and response-to-resource binding. Both `startSmartCreate` and the auto branch of `handleStart` use the same helper. Fast Mode uses the same recovery contract rather than component-only task state.

Additional corrections required by the recovery flow:

- async submit uses a short submit timeout instead of the blocking-scenario 300-second timeout;
- Fast active job and result recovery survive component remount/reload;
- Scenario recovery restores the active label and progress view;
- `completed`, `completed_bounded`, and `completed_full` are terminal consistently in progress surfaces;
- browser abort/cancel copy states that it stops waiting or hides progress and does not claim to cancel server execution;
- polling failure exposes an explicit continue-query action.

## 10. Security and observability

- Key hashing uses SHA-256; raw values never enter server-side database/filesystem persistence, structured logs, access paths, responses, traces, screenshots, or metrics labels.
- The browser's minimal pending-submission record is the single allowed raw-key persistence location. It contains no payload or credential and is browser-profile scoped, not trusted as tenant authority. Every recovery call is authenticated again by the server; if the browser API key/account changed, the record is preserved and the UI asks the user to restore the original account rather than deleting it or creating a new submission. The record is cleared only after terminal handling or explicit abandonment.
- Request hashing never serializes `api_keys` or authentication material.
- Cross-tenant lookup and status behavior remains indistinguishable from unknown resource behavior.
- Production cannot submit when the durable PG authority is unhealthy.
- Logs may include record ID, operation, scenario, resource ID, lifecycle transition, and event type (`claimed`, `replayed`, `conflict`, `recovery_required`), but not raw key, request payload, provider key, or unsanitized exception.
- Optional audit events are supplementary; the database ledger is the authority.
- CORS must allow `Idempotency-Key`. The API returns replay state in JSON, so no new exposed response header is required.

## 11. Schema and rollout boundary

Implementation updates all schema sources together:

- one Alembic revision descending from current head `7c4b8e2f1a09`;
- `src/storage/migrations/001_init.sql`;
- SQLite table initialization/backfill path;
- required-table health verification;
- schema contract and backup/restore table-set expectations where applicable.

Migration behavior is verified only against disposable PostgreSQL 18 and isolated SQLite during local development. Applying the migration to production and deploying the code require separate authorization.

When separately authorized, production rollout order is backup and rollback preflight, schema migration, required-table/read-only verification, application deployment, and no-token smoke. Code rollback leaves the additive table in place. Table downgrade/removal is never part of an application rollback and requires a later explicit data-retention decision after the older application is stable.

Existing repository-owned async callers are upgraded in the same batch. External callers that omit the header receive the documented `400` and must migrate; there is no server-generated compatibility key because a lost first response would make that key unrecoverable.

## 12. Test and acceptance requirements

### 12.1 Canonicalization and repository

- object key order does not change the request hash;
- omitted and explicit defaults hash identically;
- list order remains significant;
- strict boolean/integer differences remain distinct;
- provider-key changes do not change the business hash and no secret reaches stored/logged data;
- same tenant/key/hash returns `owner` then `replay`;
- same tenant/key with changed payload, operation, scenario, or policy returns `conflict`;
- different tenants may independently use the same raw key;
- concurrent PostgreSQL and SQLite claims produce exactly one owner;
- reconstructing repository/app state still resolves the original resource;
- terminal compare-and-set cannot be overwritten by a late callback;
- production PG/table failure returns `503` before any downstream invocation.

### 12.2 HTTP and execution

- missing, duplicate, malformed, or oversized header fails before execution;
- body `idempotency_key` remains `422`;
- CORS preflight accepts `Idempotency-Key`;
- Fast and parameterized S1-S5 same-payload replay return the same resource;
- different payload returns `409` without changing the original job;
- unknown and cross-tenant readback both return `404`;
- Fast duplicate/concurrent submit creates one task and calls the service once;
- Scenario duplicate/concurrent submit initializes one state and registers one background execution;
- S1/S3 translation executes exactly once under concurrent duplicate requests;
- response-loss simulation followed by readback returns the original job without another provider boundary;
- terminal Fast result survives process/repository reconstruction;
- stale nonterminal lease produces `recovery_required`, not a new task.

### 12.3 Frontend

- key is persisted before fetch;
- same action keeps one key through ambiguity and recovery;
- timeout, network failure, relevant 5xx, and dispatched abort enter GET readback;
- readback recovery binds the original Scenario/Fast job and resumes polling;
- exhausted readback preserves an unknown pending record and never posts again;
- `409` does not generate a replacement key automatically;
- reload performs only readback/status GETs;
- persisted state contains no payload or credentials;
- all terminal lifecycle values stop polling consistently;
- cancel and retry copy match actual server behavior.

### 12.4 Final gates

The local completion gate includes:

- focused backend repository/router/restart/CORS tests;
- disposable PostgreSQL 18 migration upgrade/downgrade and fresh-init parity;
- SQLite persistence/concurrency tests;
- focused frontend unit/component tests and UI-only recovery E2E with fake routes;
- full backend Ruff and pytest gate;
- full frontend Vitest, ESLint, TypeScript, and Next production build;
- OpenAPI regeneration and generated-type diff review;
- `git diff --check`, changed-file secret scan, and independent spec/security review;
- roadmap, API reference, runbook, SDD report, and project-state synchronization.

Completion remains local only: `production unchanged`, `provider_call=false`.

## 13. Rejected alternatives

### Optional header with a server-generated fallback key

Rejected because the client cannot recover a server-generated key when the first response is lost. It cannot complete W1-13.

### Reuse `pipeline_states` and the Fast in-memory registry

Rejected because current state persistence uses read-then-create/update behavior rather than an atomic cross-worker claim, and Fast state disappears on restart.

### Require idempotency on every mutation immediately

Rejected as an unsafe scope expansion. Gate, regenerate, publish, delivery, and blocking responses have different authority, result-size, and recovery contracts and require their own designs.

## 14. References

- `docs/superpowers/specs/2026-07-11-enterprise-ai-content-all-scenarios-closure-design.md`
- `docs/workflows/enterprise-ai-content-all-scenarios-roadmap-20260711.md`
- `docs/superpowers/plans/2026-07-11-enterprise-ai-content-wave1a-access-submit-safety.md`
- PostgreSQL `INSERT ... ON CONFLICT`: <https://www.postgresql.org/docs/current/sql-insert.html>
- SQLite UPSERT: <https://www.sqlite.org/lang_UPSERT.html>
- FastAPI header parameters: <https://fastapi.tiangolo.com/tutorial/header-params/>
- IETF HTTPAPI Idempotency-Key Internet-Draft: <https://datatracker.ietf.org/doc/html/draft-ietf-httpapi-idempotency-key-header>
