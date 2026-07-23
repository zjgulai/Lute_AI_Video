---
title: "W4 Transparency and C2PA Local Closure Plan"
doc_type: workflow
module: transparency
topic: c2pa-local-closure
status: stable
created: 2026-07-22
updated: 2026-07-23
owner: self
source: human+ai
---

# W4 Transparency and C2PA Local Closure Plan

**Scope:** Local-only closure for W4-01–W4-05. W4-06 owner/legal scope, W4-07
production certificate/HSM/KMS, and W4-08 independent external validator/platform
retention remain external gates. No provider mutation, production change, real publish,
delivery, certificate request, secret access, or external validator upload is allowed.

**Current official baseline (checked 2026-07-22):** Pin `c2pa-python==0.36.0` through
`pyproject.toml + uv.lock`. Use the current official `Signer.from_info`, `Builder.sign` or
`Builder.sign_file`, and `Reader` readback APIs; do not use the repository's old
`create_signer` or `sign_file(..., signer=...)` shape. A signing function returning a path
is not verification evidence.

**Completion truth:** Every behavior change starts with a failing contract and receives
the smallest compatible implementation. Each sub-batch passes focused and expanded local
gates, then the existing independent read-only six-dimension reviewer verifies
requirements, logic, edge cases, code quality, test coverage, and actual results. The main
thread fixes accepted findings and the same reviewer repeats until `PASS / APPROVE` or a
concrete blocker remains.

## Batch F1 — Strict transparency schema and calibrated C2PA adapter (W4-01/W4-03)

### Task 1 — Versioned transparency sidecar

**RED:** reject unknown fields, client-selected authority, non-canonical timestamps,
unsafe paths, booleans used as integer facts, invalid SHA-256, missing generation facts,
unknown content kinds, broken parent references, duplicate record IDs, and mismatched
content/file bytes. Prove canonical serialization and digest stability without storing raw
prompt, generated text, credential, or absolute path.

**GREEN:** add strict `transparency-sidecar.v1` models for text, image, audio, and video.
Each record binds tenant, scenario/resource, producer step, provider/model or explicit
local/simulated origin, UTC generation time, content kind, canonical relative artifact
identity or inline content digest/byte length, ordered parent record IDs, source references,
human-edit facts, AI-generated label, and C2PA status. The sidecar itself has a detached
SHA-256 and atomic/no-clobber write/validate helpers. It stores hashes and bounded facts,
not raw generated content.

### Task 2 — Current pinned C2PA adapter

**RED:** the old API shape must fail a source contract. Required-signing mode must fail
closed for missing SDK/cert/key, unsafe input/output, signing exception, missing output,
Reader failure, absent active manifest, wrong action/source type, or byte mismatch. Disabled
local-draft mode must not import C2PA or read certificate paths and may only return explicit
`unsigned_pending_review`, never `signed`.

**GREEN:** pin `c2pa-python==0.36.0` via uv. Implement one typed adapter using the current
official `C2paSignerInfo` + `Signer.from_info` + `Builder` API, write to an exclusive
temporary output, read it back with `Reader`, validate the active manifest, exact AI-generated
action, claim signature, and data hash, then atomically expose the signed file as
`signed_local_readback` rather than trusted/external validation. On required-signing failure,
remove partial output and raise a stable secret-safe error. Local fixture certificates are
test evidence only and never production trust evidence.

### Task 3 — F1 verification and independent review

Run focused schema/adapter tests, a real local fixture sign/readback when the pinned wheel
supports the host, locked dependency/import checks, Ruff, scoped Pyright, diff/docs/secret
gates, and affected backend tests. Then run the same independent review/reverification loop.

## Batch F2 — All-producer provenance and delivery gate (W4-04/W4-05)

**Status (2026-07-23):** `completed_local / independent_review=true`. Independent review
round 1 found four accepted issues: Gate approval bypassed the provenance boundary,
PostgreSQL state omitted the transparency projection, same-path media regeneration could
invalidate an older sidecar, and S2 external references were presented as completed producers.
The main thread fixed all four. Reverification found and the main thread fixed one remaining
filesystem strict-normalization gap; the same reviewer then returned `PASS / APPROVE` with
`accepted_actionable_findings=0`. Final backend CI is `4261 passed`, real PG18 is `7 passed`,
source Pyright is `0 errors`, and the external-action boundary remained closed.

### Task 4 — Fast and S1–S5 producer coverage

**RED:** parameterized no-provider tests must enumerate every canonical text/image/audio/
video producer in Fast and S1–S5 and fail if any completed output lacks a record. Regeneration
must create a new child record without mutating its predecessor. Human step edits must append
an edit record. Simulated/missing media must never be represented as verified real bytes.

**GREEN:** record provenance at the shared StepRunner completion boundary and the independent
Fast boundary, with a finite reviewed step-kind map. Persist the canonical sidecar inside the
tenant/disposition/run scope and project only its relative path/digest/status into durable
state. File records hash actual scoped bytes; structured/text outputs hash canonical JSON.
Regeneration and edits extend an immutable parent chain.

### Task 5 — One signing/verification boundary and fail-closed acceptance

All final image/video producers call one server-owned policy boundary. When policy is
`required`, missing SDK/certificate/signature/readback verification blocks artifact
acceptance and therefore publish/delivery. When policy is `local_draft`, unsigned artifacts
remain `pending_review`, with `publish_allowed=false` and `delivery_accepted=false`. The
acceptance fingerprint binds the exact transparency sidecar digest and final artifact C2PA
status; publish revalidates both before consuming authority. No client field may select or
relax the policy.

### Task 6 — F2 verification and independent review

Run parameterized Fast/S1–S5 no-provider coverage, regeneration/edit chain tests, acceptance/
publish fail-closed regression, disposable PostgreSQL 18 persistence parity if schema changes,
full backend/frontend contracts, Ruff/Pyright/OpenAPI, and the same review loop.

## Batch F3 — Visible labels, download package, and server metadata (W4-02)

**Status (2026-07-23):** `completed_local / independent_review=true`. Fast and S1–S5 expose the
AI-generated label and tenant-bound read-only disclosure/package projection; acceptance and
server-owned TikTok/Shopify metadata bind exact transparency truth. Independent review found one
High validate-to-package TOCTOU; the main thread bound the exact validated sidecar/detached bytes
in a frozen snapshot, and the same reviewer returned `PASS / APPROVE` with
`accepted_actionable_findings=0`. Final backend CI is `4273 passed`, frontend is `71 files / 438
tests`, UI-only desktop/mobile is `4 passed`, and source Pyright is `0 errors`. W4-06/W4-07/W4-08
remain external and no provider, production, publish, or delivery mutation occurred.

### Task 7 — UI and download truth

Expose a strict read-only transparency projection. Result/review UI displays AI-generated,
signed-and-locally-read-back, or unsigned-pending-review truth without implying legal trust.
Download packages include the exact sidecar and detached digest. Missing or inconsistent
sidecars fail closed rather than hiding the label.

### Task 8 — Publish metadata and documentation

Server-owned TikTok/Shopify metadata adds the visible AI-generated disclosure from the
validated sidecar; the client cannot remove it. Synchronize the ADR/runbooks to distinguish
engineering provenance from legal compliance and local Reader verification from W4-08
independent validation. Remove obsolete graceful-degradation and outdated API instructions.

### Task 9 — F3/full W4 local verification and independent review

Run frontend unit/accessibility/mobile checks, download/OpenAPI/publish metadata contracts,
full backend/frontend/locked build gates, docs governance, secret scans, and the same reviewer
until approval. Mark only W4-01–W4-05 complete locally.

## External evidence boundary

- W4-06: owner/legal records exact provider/deployer/geography scope and EU policy.
- W4-07: trusted production certificate and private-key custody through HSM/KMS/secret mount.
- W4-08: independent validator and target-platform preservation on a real authorized sample.
- Production deployment of this local branch remains blocked by the reviewed `origin/main`
  provenance requirement; no mutable-source or direct-rsync substitute is allowed.
