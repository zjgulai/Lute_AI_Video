---
title: "W4-09-W4-13 Documentation Version And Operations SSOT Plan"
doc_type: workflow
module: release-governance
topic: documentation-version-security-ssot
status: active
created: 2026-08-01
updated: 2026-08-01
owner: self
source: human+ai
---

# W4-09–W4-13 Documentation, Version and Operations SSOT Plan

## Status and boundary

`completed_local / independent_review=true`. This plan authorized only local tracked implementation,
tests, documentation and read-only review. It does not authorize staging,
commit, push, PR, deployment, provider or W5 execution, publish, or delivery.
The maximum evidence for this batch is L2 local/static/fixture evidence. Earlier
L3 production read-only health does not prove this candidate is deployed.

## Objective

Close the operator-facing ambiguity that can turn an otherwise reviewed image
candidate into the wrong release: one semantic-version authority, a separate
immutable source revision, one permission contract, one production operations
entry point, machine-enforced dangerous-command boundaries, and one current
backlog separated from history.

## Execution TODO

### W4-09 — release identity

- [x] RED: fail when package/frontend/OCI/release documentation versions drift.
- [x] RED: fail when health or images omit immutable source revision.
- [x] GREEN: derive semantic version from `pyproject.toml`, expose a check-only
  version utility, and bind image labels/build arguments to the same value.
- [x] GREEN: expose validated semantic version and source revision as separate
  health facts; never infer deployed source from semantic version.
- [x] GREEN: record `v2.0.0` only as the expected tag until an authorized tag
  actually exists.

### W4-10 — authentication and permissions

- [x] RED: compare the machine-readable permission contract with
  `_RECOGNIZED_TENANT_PERMISSIONS` and production test-bundle behavior.
- [x] GREEN: document tenant API-key, environment fallback, test-bundle, and
  admin cookie/CSRF planes without embedding credentials.
- [x] GREEN: remove claims that the test/demo key is read-only or is the real
  production credential.

### W4-11/W4-12 — canonical operations and destructive safety

- [x] RED: scan active operating docs and entry scripts for prohibited live
  `down --volumes`, insecure SSH, secret extraction, repository-root private
  keys, and unreviewed destructive rsync patterns.
- [x] GREEN: designate one production operations index and one canonical owner
  each for deploy, DR and token smoke.
- [x] GREEN: reduce duplicate deployment SOPs to non-copyable historical
  pointers and quarantine legacy scripts from default/canonical entry points.
- [x] GREEN: keep the governance list explicit so historical evidence can
  remain readable without becoming executable guidance.

### W4-13 — current backlog versus history

- [x] RED: require a tracked current backlog in the blocking documentation
  scope and reject ignored journals as mandatory build/release inputs.
- [x] GREEN: add the concise current backlog, mark the large known-gaps ledger
  append-only historical, and update active entry points.

## Verification and review

- [x] Run focused RED/GREEN tests first.
- [x] Run Ruff, scoped Pyright, Bash syntax, docs/frontmatter/link/archive
  governance, diff checks and secret scans.
- [x] Run proportional backend, frontend, rendering, OpenAPI, recovery and
  release regression lanes without provider or production access. All
  source/application lanes are green; the final combined Docker rebuild is
  blocked before build execution by unreachable Docker Hub OAuth over both
  IPv4 and IPv6. Existing H10.3 image evidence must not be relabeled as the
  combined W4 candidate.
- [x] Give the final combined H10 plus W4 candidate to an independent read-only
  reviewer for requirement completeness, logic correctness, boundary cases,
  code quality, test coverage and actual runtime results.
- [x] Fix every accepted finding in the main thread and ask the same reviewer
  to recheck until PASS/APPROVE or a concrete blocker.
- [x] Freeze the exact path list and content-manifest digest in the optional
  local progress journal, then stop before Git mutation.

## Final local evidence

- Backend: `4573 passed, 9 skipped, 24 deselected`.
- Frontend: `71 files / 439 tests`; ESLint and OpenAPI drift green.
- Rendering: `16 tests`; TypeScript and production dependency audit green.
- Recovery: `95 passed`; Hermetic S1-S5: `283 passed`.
- Source Pyright: `0 errors`; test ratchet, Ruff, Bash syntax, semantic-version
  projection, docs/diff/secret governance green.
- Independent review required ten same-thread passes. The final three passes
  closed complete-worktree archive governance, dirty-worktree test isolation,
  and precise test helper typing. Final result: `PASS / APPROVE`,
  `accepted_actionable_findings=0`.
- Fresh combined-image build evidence remains unavailable because Docker Hub
  OAuth was unreachable before Dockerfile execution over both IPv4 and IPv6.
  Existing H10.3 image/scan receipts are not relabeled as this W4 candidate.

This is L2 local source/application evidence, not production deployment,
provider execution, publish/delivery, or fresh combined-image acceptance.

## Fail-closed stop rules

Stop the batch on any active High/Critical image finding, version or source
identity contradiction, undocumented permission, active copyable destructive
command, missing current backlog owner, secret exposure, provider attempt,
production mutation, or inability to reproduce the claimed test evidence.
