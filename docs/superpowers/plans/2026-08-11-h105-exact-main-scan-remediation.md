---
title: "H10.5 exact-main vulnerability scan remediation plan"
doc_type: workflow
module: release-security
topic: h105-exact-main-scan-remediation
status: stable
created: 2026-08-11
updated: 2026-08-11
owner: self
source: human+ai
---

# H10.5 Exact-main Vulnerability Scan Remediation Plan

**Status:** `completed_local / independent_review=true`

**Design authority:**
`docs/superpowers/specs/2026-08-11-h105-exact-main-scan-remediation-design.md`,
SHA-256
`4fd67008df3776b308d16239136d131d0a13dac4b661bd4063118d1bb5c0ce85`.

**Scope:** local non-Docker implementation, verification, and independent
read-only review only. No stage, commit, push, PR mutation, workflow dispatch,
image build, scanner execution, deployment, production action, provider
mutation, W5 submit, publish, or delivery is authorized.

## Objective

Create one exact H10.5 source candidate that remediates the fixed Node findings,
calibrates only the scanner states proven by run `31479125469`, and constrains
the remaining PyAV/libssh2 findings with exact component-scoped rules that
expire fail-closed on the existing date.

## Execution TODO

### P1 — Freeze evidence and add RED contracts

- [x] Record the exact run, source SHA, artifact ID/digest, scanner version,
  database timestamp, and database checksum in the approved design.
- [x] Confirm the exact sixteen FFmpeg CVEs whose 288 state-bound rules stopped
  matching because Grype changed `not-fixed` to `wont-fix`.
- [x] Confirm the eight backend PyAV FFmpeg binary findings, two renderer
  libssh2 findings, and three fixable renderer Node findings.
- [x] Update `tests/test_h10_iamf_remediation.py` to require the exact Node
  22.23.2 digest and reject the superseded digest.
- [x] Update `tests/test_vulnerability_scan_policy.py` with RED assertions for
  the exact state map, component-scoped new CVEs, expiry, isolation, counts,
  and canonical digests.

### P2 — Apply the minimal implementation

- [x] Update only the renderer `NODE_IMAGE` digest in
  `rendering/Dockerfile`.
- [x] Change only the 288 evidenced H10.4 Grype `fix-state` values in
  `.grype-backend.yaml` and `.grype-rendering.yaml`.
- [x] Add exactly eight backend-only `ffmpeg 8.1.2 binary unknown` Grype rules
  and their exact expiring Trivy counterparts.
- [x] Add exactly two renderer-only `libssh2-1t64 1.11.1-1+deb13u1
  not-fixed` Grype rules and their exact expiring Trivy counterparts.
- [x] Recompute all four changed policy inventories and canonical SHA-256 set
  digests independently; update only the pinned expected values.
- [x] Update `docs/runbooks/vulnerability-scan-exceptions.md` with the exact
  failure evidence, remediation rationale, new inventories, and L2 boundary.

### P3 — Non-Docker provider-off verification

- [x] Pass focused H10, vulnerability-policy, safe-media/PyAV ordering,
  deploy-workflow, and documentation-governance tests.
- [x] Pass expanded affected backend tests without provider/network mutation.
- [x] Pass Ruff, YAML parse, shell syntax, project-version, diff, and bounded
  candidate secret checks.
- [x] Prove no unrelated tracked file changed and preserve the user's
  `scripts/space_governance.py` file untouched.

### P4 — Independent six-dimension review loop

- [x] Freeze the exact candidate path/size/SHA manifest and canonical digest.
- [x] Start one independent read-only review thread covering requirement
  completeness, logic, edge cases, code quality, test coverage, and actual
  execution results.
- [x] Return every accepted actionable finding to the main thread, add a RED
  regression, fix it, and ask the same reviewer to re-verify.
- [x] Stop only at `PASS / APPROVE` with
  `accepted_actionable_findings=0`, or report the precise remaining blocker.

### P5 — Close the local gate

- [x] Mark this plan `completed_local / independent_review=true` only after P4
  passes.
- [x] Report the frozen candidate identity and the next separately authorized
  exact-image build/SBOM/Trivy/Grype gate.
- [x] Do not stage, commit, push, dispatch, build images, or deploy.

## Expected Candidate Files

1. `.grype-backend.yaml`
2. `.grype-rendering.yaml`
3. `.trivyignore-backend.yaml`
4. `.trivyignore-rendering.yaml`
5. `rendering/Dockerfile`
6. `tests/test_h10_iamf_remediation.py`
7. `tests/test_vulnerability_scan_policy.py`
8. `docs/runbooks/vulnerability-scan-exceptions.md`
9. `docs/superpowers/specs/2026-08-11-h105-exact-main-scan-remediation-design.md`
10. `docs/superpowers/plans/2026-08-11-h105-exact-main-scan-remediation.md`

No other path is authorized unless an accepted reviewer finding demonstrates
that a directly related contract cannot be closed within these files.

## Local Verification Record

- TDD RED stabilized at `8 failed, 27 passed` before the implementation; the
  focused GREEN run is `35 passed`.
- Expanded affected verification is `237 passed` with no provider or network
  mutation.
- Whole-worktree pytest reached `4585 passed, 9 skipped, 24 deselected`; its
  only two failures are the existing governance classification checks for the
  explicitly excluded user file `scripts/space_governance.py`. The H10.5
  candidate does not modify, move, classify, or otherwise touch that file.
- Direct HEAD-to-candidate policy comparison proves exactly 144 state-only
  changes in each Grype file, plus exactly eight backend and two renderer new
  component rules. Every pre-existing Trivy rule remains semantically
  unchanged, with exactly eight backend and two renderer additions.
- Ruff, YAML parse, shell syntax, project version `2.0.0`, and scoped diff
  checks pass. No Docker or scanner execution was performed.
- Independent review round 1 accepted one Medium documentation drift: the
  standing rule still described six PyAV binary records after H10.5 raised the
  exact backend inventory to fourteen. A new regression reproduced the stale
  wording as RED; the runbook now states original `6` plus H10.5 `8`, total
  `14`, and the focused post-fix verification is `43 passed`.
- The same independent review thread then ran a fresh `174 passed`, Ruff,
  target Pyright, project-version, diff, and manifest verification. Final
  verdict is `PASS / APPROVE` with `accepted_actionable_findings=0`.

## Evidence Boundary

Passing this plan supports only `L2-fixture-or-dry-run` source-candidate truth.
It does not prove that an H10.5 image builds, that the current scanner database
classifies every High/Critical match, that a release archive exists, or that
production is deployable. Those claims require the later exact-image and
exact-main archive gates.
