---
title: "H10.5 exact-main vulnerability scan remediation"
doc_type: architecture
module: release-security
topic: h105-exact-main-scan-remediation
status: review
created: 2026-08-11
updated: 2026-08-11
owner: self
source: human+ai
---

# H10.5 Exact-main Vulnerability Scan Remediation

## Context

The exact-main `archive-only` GitHub Actions run `31479125469` built the three
release images for source revision
`85dd0b6e53d04c1196fc22687315ffc03871495f`. Provenance, preflight, image
builds, runtime smoke, and SBOM generation passed. The release then failed
closed at the High/Critical Grype enforcement step, so no release archive or
archive checksum was produced. Remote dry-run and production deployment were
skipped.

The uploaded scanner evidence used Grype `0.110.0` with vulnerability database
`v6.1.9`, timestamp `2026-08-11T00:23:43Z`, and database checksum
`sha256:5a05533116ce3db9d8ebf8b6f946c90bc56b1b0a477c11dd099f3c7f130af1f7`.
Its exact evidence artifact is
`vulnerability-scan-85dd0b6e53d04c1196fc22687315ffc03871495f`, artifact ID
`9097621866`, with digest
`sha256:1cc1d1dd8199ba8acf4a7975e642f1048220e77a3973ee4478ec0d9143904c02`.

The failure has four distinct causes and they must not be collapsed into one
broad scanner exception:

1. The renderer contains Node `22.23.1`; three High findings are reported as
   fixed in `22.23.2`.
2. Sixteen exact FFmpeg CVEs across nine H10.4 Debian packages changed from
   Grype `not-fixed` to `wont-fix`. The repository's exact state-bound rules no
   longer match, producing 144 active High records in each of backend and
   renderer.
3. The backend PyAV `18.0.0` wheel contains FFmpeg `8.1.2`; eight newly
   reported High findings have an empty scanner fix state, which Grype matches
   through the repository's `unknown` state convention.
4. The renderer contains `libssh2-1t64 1.11.1-1+deb13u1`; two new High findings
   remain `not-fixed` in the scan and undetermined in Debian's tracker.

## Goals

1. Remediate every fixable finding instead of suppressing it.
2. Calibrate scanner state only for the exact CVE, package, version, and type
   observed in the immutable scan evidence.
3. Keep unavoidable exceptions component-scoped, reasoned, expiring, and
   fail-closed.
4. Preserve the existing H10.4 FFmpeg patches, media validation boundary,
   provider-off runtime behavior, and release workflow enforcement.
5. Produce a locally reviewed H10.5 candidate that is ready for a separately
   authorized exact-image rebuild and scan.

## Non-goals

- Weaken the High/Critical enforcement threshold or set `only-fixed`.
- Add severity-wide, package-wide, CVE-only, or non-expiring ignores.
- Claim that PyAV FFmpeg or libssh2 is patched when only isolation and
  reachability controls exist.
- Replace Chrome packaging, split transcription into another service, or build
  a custom FFmpeg 8/PyAV toolchain in this bounded remediation.
- Run Docker, stage, commit, push, open or update a PR, dispatch a workflow,
  deploy, call a provider, submit W5, publish, or deliver.

## Decision

Use a layered remediation: upgrade the fixable Node runtime; update only the
scanner states proven to have drifted; add exact short-lived component-specific
records for the PyAV and libssh2 findings that have no currently installable
fix; and lock all of these choices with negative regression tests.

This is preferable to a large Chrome/PyAV supply-chain redesign because it
closes the immediate exact-main gate with bounded, auditable changes while
preserving fail-closed expiry. It is preferable to waiting indefinitely because
the remaining unfixed findings are already behind explicit local-file or
network-isolation boundaries that can be tested directly.

## Component Design

### 1. Renderer Node upgrade

Change the renderer's overrideable, digest-pinned base image to:

```text
node:22.23.2-trixie-slim@sha256:db8a96a63e5264607ada2d206758876ebbed6a12be2ada7517793cbfb0c2a29c
```

A read-only Docker Registry lookup resolved this index to linux/amd64 manifest
`sha256:f4c1b09232a0ae8f765093968ec82107a1be65cb0bfb36fc831195794f139568`
and config
`sha256:51b44aa21c7566febf150556ac5fdbfda9bf7a4575177f9b353e585a835b803b`,
whose environment declares `NODE_VERSION=22.23.2`.

The existing Dockerfile remains multi-stage and overrideable. Tests must pin
the exact image string and prevent fallback to a floating or unqualified tag.
No Node CVE exception is added.

### 2. H10.4 FFmpeg Grype state calibration

For exactly these sixteen CVEs, update only the Grype `fix-state` field from
`not-fixed` to `wont-fix` for all nine exact H10.4 Debian runtime packages in
both backend and renderer policies:

- `CVE-2026-64830` through `CVE-2026-64835`
- `CVE-2026-65703` through `CVE-2026-65706`
- `CVE-2026-66036`
- `CVE-2026-66039` through `CVE-2026-66041`
- `CVE-2026-70628`
- `CVE-2026-70632`

The package names, exact version
`7:7.1.5-0+deb13u1+h10.4`, package type `deb`, CVE set, and Trivy statements
remain unchanged. `CVE-2026-66037` and `CVE-2026-66038` are not changed because
the failure evidence did not show state drift for them.

The two H10.4 backported CVEs continue to be scanner false positives only
because their checksum-bound upstream patches remain present and verified.
Changing scanner state does not replace or weaken that source-level proof.

### 3. Backend PyAV FFmpeg records

PyAV `18.0.0` is the current release and its published Linux wheel bundles
FFmpeg. PyAV 18's documented source build targets FFmpeg 8.x, while the
repository's checksum-bound H10.4 system FFmpeg is 7.1.5. A source rebuild
against H10.4 is therefore not treated as a safe drop-in remediation.

Add backend-only Grype records for:

- `CVE-2026-65703` through `CVE-2026-65706`
- `CVE-2026-66036`
- `CVE-2026-66039` through `CVE-2026-66041`

Every rule must bind `fix-state: unknown`, package `ffmpeg`, version `8.1.2`,
and type `binary`. Add matching backend-only Trivy records for
`pkg:generic/ffmpeg@8.1.2`, expiring on `2026-08-21`.

The justification is limited to the existing transcription path: input bytes
must pass `validate_media_file` before PyAV or `WhisperModel` construction;
only validated local files reach the decoder; unsupported container, codec,
filter, muxer, device, and network paths remain outside the call contract.
Tests must prove the exact eight-CVE inventory, backend-only placement, common
expiry, and validate-before-PyAV-import ordering. No statement may describe the
embedded FFmpeg as fixed.

### 4. Renderer libssh2 records

Add renderer-only records for `CVE-2026-58050` and `CVE-2026-58051`, each
binding `fix-state: not-fixed`, package `libssh2-1t64`, version
`1.11.1-1+deb13u1`, and type `deb`. Add matching Trivy purls, expiring on
`2026-08-21`.

The statement is limited to runtime isolation: the renderer joins no Docker
network because both release Compose contracts set `network_mode: none`; it
receives local validated media snapshots and has no SSH, SFTP, SCP, or libssh2
call path. Tests must lock all four facts and prove these records do not appear
in the backend or shared policies. The exception becomes invalid if the
renderer obtains egress or any SSH-family feature.

### 5. Policy inventory and documentation

Recompute the canonical count and SHA-256 set digest for each changed Grype and
Trivy policy. Tests continue to reject duplicate, incomplete, unversioned, or
unexpected rules. The runbook records:

- exact GitHub run, revision, scanner DB, and artifact identity;
- finding counts and the four-way classification above;
- the Node digest and registry resolution evidence;
- exact rule additions and state-only changes;
- unchanged `2026-08-21` expiry and `2026-08-22` fail-closed behavior;
- the fact that no H10.5 image, SBOM, runtime smoke, or scanner result exists
  until the separately authorized image gate runs.

## Error and Failure Behavior

- A Node image string or digest mismatch fails static tests.
- Any FFmpeg state change outside the sixteen proven CVEs fails the canonical
  inventory tests.
- Any PyAV rule outside backend, any libssh2 rule outside renderer, or any
  shared-policy leakage fails tests.
- Any missing package version/type, missing reason, missing owner, or changed
  expiry fails tests.
- The existing expiry helper must pass on `2026-08-21` and fail on
  `2026-08-22`.
- A future scanner DB state change fails the exact scan again; policy is not
  automatically rewritten from scanner output.
- Local static success remains L2 candidate evidence and cannot authorize a
  release archive or production action.

## Verification Strategy

1. Add RED assertions for the Node 22.23.2 digest, the exact FFmpeg state map,
   the expanded PyAV eight-CVE set, the two libssh2 records, component
   isolation, and expiry behavior.
2. Apply the smallest Dockerfile and policy changes that make those assertions
   green.
3. Recompute policy counts and canonical digests independently, then update
   the pinned expectations and runbook.
4. Run focused H10 and vulnerability-policy tests, safe-media/PyAV ordering
   tests, workflow scan-policy tests, Ruff, shell syntax, YAML parsing,
   documentation governance, diff checks, and a bounded secret scan.
5. Run the relevant expanded provider-off backend suite without Docker or
   external network mutations.
6. Start an independent read-only six-dimension review covering requirements,
   logic, edge cases, code quality, test coverage, and actual test results.
   Return every accepted finding to the main thread, fix it, and ask the same
   review thread to re-verify until it approves or reports a concrete blocker.

## Evidence Grades and Rollout Gates

1. **Design gate:** this specification is approved.
2. **Local implementation gate:** static, fixture, and provider-off tests plus
   independent review may establish only L2 candidate evidence.
3. **Git gate:** exact staging, commit, and push require separate authority.
4. **Image gate:** local or GitHub exact-image build, runtime smoke, SBOM, and
   fresh Trivy/Grype scans require separate authority and new evidence.
5. **Archive gate:** only a successful exact-main `archive-only` run can
   produce the release archive and checksum.
6. **External gates:** remote dry-run, production deploy, provider, W5,
   publish, and delivery remain independently prohibited.

## Acceptance Criteria

- The renderer uses the exact Node 22.23.2 digest and has no exception for the
  three fixed Node findings.
- Exactly 288 H10.4 Grype records change state: sixteen CVEs across nine
  packages in two component policies, with no package/version/CVE drift.
- Exactly eight backend-only PyAV binary CVEs and two renderer-only libssh2
  CVEs are represented in both Grype and Trivy with exact identity and expiry.
- Existing H10.4 patch checks, media validation, renderer isolation, scan
  enforcement, and expiry failure behavior remain green.
- Focused and expanded non-Docker verification passes.
- Independent review returns `PASS / APPROVE` with
  `accepted_actionable_findings=0`, or the remaining blocker is reported
  precisely.
- No Docker, Git mutation, GitHub mutation, deploy, production, provider, W5,
  publish, or delivery action occurs in this local gate.
