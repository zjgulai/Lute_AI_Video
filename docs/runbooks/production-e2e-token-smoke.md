---
title: Production E2E Provider Safety Boundary
doc_type: workflow
module: ci-cd
topic: production-e2e-token-smoke
status: stable
created: 2026-05-31
updated: 2026-08-01
owner: self
source: human+ai
---

# Production E2E Provider Safety Boundary

## Current executable behavior

`.github/workflows/e2e-prod.yml` currently executes only the public read-only
Playwright job. The public read-only job intentionally receives no API key or
repository/Environment secret. Authenticated checks therefore skip, and the
result is partial public evidence rather than authenticated L3 acceptance.

The `e2e-prod-token-smoke` job is hard-disabled with an unconditional false
job condition. `token_smoke_spec`, `approval_record_path`, `plan_path`,
`RUN_TOKEN_SMOKE=1`, and `@token-smoke` remain only as dormant compatibility
contract names. They cannot enable execution through workflow inputs, secrets,
environment protection, branch selection, or manual dispatch.

The demo key `ai_video_demo_2026` is never a production credential. No current
path supports “only after recharge” execution. A new paid-provider test must
use a fresh governed W5 exact-authorization plan; it may not reuse P2/C21,
L4C, generic token-smoke, or previous W5 authority.

## Dormant L4C contract reference

The disabled job is retained temporarily so historical evidence remains
interpretable and so removal can be a separately reviewed migration. It is not
an operational recipe. Its frozen design had the following safety intent:

- `PROD_TOKEN_SMOKE_API_KEY` was scoped only to the validation and token
  execution steps.
- `PROD_TOKEN_SMOKE_PLAN_B64` and `PROD_TOKEN_SMOKE_APPROVAL_B64` were decoded
  into `$RUNNER_TEMP/l4c-token-smoke-plan.json` and
  `$RUNNER_TEMP/l4c-token-smoke-approval.json`.
- Base64 is transport encoding, not encryption.
- User-supplied `plan_path` and `approval_record_path` were a logical audit ref,
  never an output path.
- The validator bound `workflow_run_ref` and `commit_sha`, required
  `approved_at<=now<expires_at`, and required
  `expires_at-approved_at<=4h`.
- The historical token mode required strict TLS and disables Playwright traces.
  It exposed credential material to only the validation and token execution steps.
- Its JSON budget was not a server-side durable reservation or hard spending cap.
  This limitation is one reason the generic path is no longer executable.

## Operator decision

- For public availability checks, run the provider-off read-only job and label
  the result partial public evidence.
- For authenticated provider-off L3 acceptance, use the canonical deployment
  and read-only acceptance procedure with a separately scoped credential.
- For any provider mutation, stop here and create a new W5 exact-authorization
  packet with immutable source, tenant/sample, model/job caps, USD-nanos budget,
  retry-zero policy, pending-review disposition, and explicit publish/delivery
  prohibition.

The hard-disabled workflow job must not be re-enabled by editing only its
condition. Re-enablement would be a new provider execution design requiring
threat review, durable budget/idempotency proof, independent six-dimension
review, protected release evidence, and fresh user authorization.
