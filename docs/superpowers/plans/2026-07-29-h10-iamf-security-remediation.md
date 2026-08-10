---
title: "H10 IAMF Security Remediation Plan"
doc_type: workflow
module: media
topic: iamf-security-remediation
status: active
created: 2026-07-29
updated: 2026-08-01
owner: self
source: human+ai
---

# H10 IAMF Security Remediation Plan

**Status:** `completed_local / independent_review=true`

**Scope:** local candidate implementation, verification and independent read-only
review only. No stage, commit, push, PR, archive, deployment, provider mutation,
W5 submit, publish or delivery is authorized.

## Objective

Remove the exploitable IAMF parsing path associated with `CVE-2026-66037` from
both backend and renderer images while preserving the existing fail-closed media
boundary and exact vulnerability-policy governance.

## Execution TODO

- [x] Bind the exact upstream IAMF allocation fix and all source inputs by
  SHA-256.
- [x] Implement the checksum-bound Debian rebuild recipe for version
  `7:7.1.5-0+deb13u1+h10.3`.
- [x] Configure that recipe to compile out the unused IAMF demuxer,
  libssh/SFTP and librist/RIST surfaces.
- [x] Wire the same nine runtime packages and fail-closed build-time verifier
  into backend and renderer image definitions.
- [x] Reject IAMF and renamed IAMF before FFmpeg or FFprobe starts.
- [x] Bind Grype and Trivy exceptions to the custom version and add nine exact
  `CVE-2026-66037` mappings.
- [x] Pass focused, policy, documentation, diff and secret checks.
- [x] Rebuild readable exact linux/amd64 backend and renderer images after the
  local Docker storage layer is recovered.
- [x] Re-verify image-internal package versions and IAMF/SFTP/RIST absence.
- [x] Regenerate SBOM and pass exact-image Grype and Trivy High/Critical gates.
- [x] Re-run constrained runtime smoke.
- [x] Complete independent six-dimension read-only review; fix and re-review
  until approved or explicitly blocked.

## Required Evidence

Static and fixture evidence cannot substitute for image evidence. Closure
requires all of:

1. exact candidate source digest and exact image digests;
2. nine installed package versions equal to the H10 custom version;
3. image-internal FFmpeg/FFprobe inventories without IAMF;
4. SBOM plus scanner JSON/checksums with zero active High/Critical findings;
5. backend and renderer runtime smoke under their canonical restrictions;
6. independent review of requirements completeness, logic, boundary cases,
   code quality, test coverage and actual runtime results.

## Superseded Pre-review Image Evidence

The pre-review runtime-input digest was
`44682e35a5a6f63fd273d007c811da509b3837300a6c7f846ed55ef1672c2453`.
It is calculated from the sorted path plus SHA-256 inventory of every tracked
backend/renderer image input and every file under `docker/ffmpeg/`; evidence
documents and scanner outputs are deliberately outside that runtime identity.

- backend image:
  `sha256:d0c6f994f58c2e178d58c726af642043e70c3d4244b2582e4dca7a68a69ba762`,
  `1234196446` bytes;
- renderer image:
  `sha256:f8801958ff292ac208c208cab76a052434f45736d363d0951f7734070f97e6af`,
  `805144191` bytes;
- both images are `linux/amd64`, run as `999:999`, carry the exact runtime
  digest label, install all nine packages at
  `7:7.1.5-0+deb13u1+h10.1`, and expose no IAMF demuxer;
- both exact images have Trivy `0 active High/Critical` and Grype
  `0 active High/Critical`; Grype classified `223` backend and `229` renderer
  High/Critical matches through exact reviewed records;
- backend application import and renderer health passed with network disabled,
  read-only rootfs, all capabilities dropped, no-new-privileges, finite CPU,
  memory and PID limits, and UID/GID-owned tmpfs mounts;
- focused tests are `45 passed`, full backend is
  `4542 passed, 9 skipped, 24 deselected`, S1-S5 hermetic is `283 passed`,
  Pyright is `0 errors`, and Ruff, Bash syntax, diff and candidate secret scans
  are green.

The first independent review subsequently found three actionable issues:
binary-only PyAV Grype exceptions were not tied to the shared Trivy expiry
gate, the runtime verifier treated failed or empty FFmpeg inventories as safe,
and the validate-before-PyAV-import boundary lacked behavioral regression
coverage. Those three issues are fixed locally.

## Superseded Docker-storage Blocker

The superseded post-review runtime-input digest was
`802f2b2ca9b297a8ad6bbbe3015e633f4b6eaf4df3ac25c0e539590f6488f1c3`.
Buildx completed both `linux/amd64` exports and Docker initially reported:

- backend:
  `sha256:e78762666d3c2c0fe2875b85a20bf01d0aa8f075674266b50272d0745d90a648`,
  `1234239532` bytes;
- renderer:
  `sha256:711d4210b77d1aaefb1ed111dddce2dca611410d404f3b6d48465fe34abe498f`,
  `805145843` bytes.

The build exhausted the local Docker Desktop storage layer. Subsequent
container creation and blob reads fail with containerd `input/output error`,
including a direct read of the new backend image blob. These image identities
therefore are not accepted as readable exact-image evidence and no current
runtime or scanner claim is made. Recovery requires an explicitly authorized
Docker Desktop restart, followed by removal of superseded H10-only
containers/images/cache and a clean rebuild.

Post-fix source evidence is:

- focused H10/policy/media tests: `57 passed`;
- full backend: `4554 passed, 9 skipped, 24 deselected`;
- S1-S5 hermetic: `283 passed`;
- source Pyright: `0 errors`;
- Ruff, Bash syntax, diff and candidate secret scans: green.

Docker Desktop was subsequently recovered under the exact one-restart and
H10-only cleanup authorization. The unreadable image identities in this section
remain superseded and are not reused by the accepted H10.3 evidence below.

## 2026-08-01 Scanner Drift Follow-up

Docker Desktop was explicitly authorized to start once and recovered with no
running application containers. Cleanup removed only superseded H10 images,
containers, builder state and scanner cache. A fresh Trivy database then found
four new High findings in Debian Trixie `libssh-4`. Debian still had no stable
fix, and this project has no SSH/SFTP media input requirement. The candidate
therefore does not add exceptions: H10.3 disables libssh at compile time, the
runtime verifier requires `libssh-4` and SFTP to be absent, and existing libssh
policy records are removed. The next accepted evidence must use a newly
calculated runtime digest and freshly rebuilt images; the H10.1 images and
scanner reports above remain superseded.

The same fresh Grype database then surfaced unused `librist4`/`libcjson1`
findings plus two Python findings whose global `fixed` state points only to a
different development branch. H10.3 removes librist/RIST and the resulting
libcjson runtime dependency instead of adding exceptions. The two Python rules
are exact package/version/type/CVE records and require `fix-state: fixed`; they
do not treat a different Python branch as an installable 3.12 fix.

## Current H10.3 Candidate Evidence

The accepted runtime-input digest is
`ca781ca2db53f1da0a5f22d04f15438bfca6249ce1fe51215699a95ab32efbe7`.
Both images are fresh `linux/amd64` exports, run as `999:999`, carry this exact
revision label, and install all nine FFmpeg runtime packages at
`7:7.1.5-0+deb13u1+h10.3`:

- backend:
  `sha256:b5f15d41b7348c2e8004ee270d591e023547af1094989103f0165ba01f4a6f35`,
  `1233579289` bytes;
- renderer:
  `sha256:251e4cc61b814ad02980e7338611c5b025286af6e731dc6e7f949b3f3a00b46b`,
  `804483561` bytes.

Image-internal verification requires non-empty FFmpeg and FFprobe inventories,
rejects IAMF, SFTP and RIST, and confirms `libssh-4`, `librist4` and `libcjson1`
are absent. Backend application import and renderer Unix-socket health both
pass with network disabled, read-only rootfs, all capabilities dropped,
no-new-privileges, finite CPU/memory/PID limits and UID/GID-owned tmpfs mounts.

Fresh exact-image evidence is:

| evidence | bytes | SHA-256 |
|---|---:|---|
| backend SPDX JSON | 3385881 | `fb4380d79a97419ddc4abd816f78718d917c3d57b6fa69b07652a5158ca120e8` |
| renderer SPDX JSON | 1487027 | `05198856e830735e0ebac66875b5c8d767ccdeea03d84f82fb317c04ca4763ce` |
| backend Trivy JSON | 1540042 | `cc39e740575995c62fd1fd54be02c673c4eee54b1c0265aeeca20eaaf3d995ba` |
| renderer Trivy JSON | 1214822 | `a4b7d2698297b1a34e0a95a9b1940f685dbdcb174855a81dcace4da27e245935` |
| backend Grype JSON | 2252188 | `90791d42b34f40f1bef89cb6670757ae18daca3b57b6a77f70d01c0d7a45c9fc` |
| renderer Grype JSON | 2499465 | `fdfe837be52cb3277caf1c7d219c80020285bda5d1c04a4e04bae8d2686a5de7` |

Trivy and Grype both report `0 active High/Critical` for each exact image;
Grype classifies `211` backend and `216` renderer matches only through exact
reviewed policy records. Both SBOMs contain the nine H10.3 packages and none of
the three forbidden packages. Focused H10 evidence is `62 passed`; full backend
is `4558 passed, 9 skipped, 24 deselected`; S1-S5 hermetic is `283 passed`;
source Pyright is `0 errors`; Ruff, Bash syntax, documentation, diff and
candidate secret gates are green.

The final reviewer found one Medium packaging-contract gap: the supported
CloudBase upload command omitted `docker/ffmpeg/` even though the backend
Dockerfile copies it. The guide now includes the complete `docker/` input,
documents the prerequisite and troubleshooting check, and a static regression
test binds the upload bundle to the H10 build context. The combined affected
and documentation recheck is `87 passed`.

The same independent reviewer completed the final six-dimension read-only
verification with `PASS / APPROVE` and `accepted_actionable_findings=0` after
the packaging-contract fix. This closes H10 locally at L2 only. No stage,
commit, push, PR, archive, deployment, provider mutation, W5 submit, publish or
delivery occurred.
