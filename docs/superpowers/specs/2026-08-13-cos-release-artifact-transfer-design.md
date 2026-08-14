---
title: "COS-backed exact release artifact transfer"
doc_type: architecture
module: ci-cd
topic: cos-release-artifact-transfer
status: review
created: 2026-08-13
updated: 2026-08-13
owner: self
source: human+ai
---

# COS-backed Exact Release Artifact Transfer

## Context

The exact-main production workflow run `31684670231` proved the existing
release archive, image, scan, and approval gates at source revision
`2a3e49c6475ee13eac3fced56348d51668c5e237`. It did not deploy the
candidate. The GitHub-hosted runner transferred only about 8.9 MB of the
2.28 GB compressed image archive in eight minutes. A direct Lighthouse to
GitHub probe received zero bytes before its 20-second timeout. The run was
cancelled before the remote deploy script, migration, backup, restore, or
application switch. Its partial candidate directory was removed after proving
that it was not current and had no candidate container.

The same run exposed two release blockers:

1. a single `rsync -avz` data stream from a GitHub-hosted runner to Lighthouse
   cannot complete the exact archive within the workflow execution window;
2. the workflow creates the final `releases-<SHA>` directory before the large
   transfer and has no repository-owned transfer-failure receipt or cleanup
   transaction.

This design replaces only the release data plane. It preserves exact-main
provenance, the reviewed `docker save` archive, image digests, provider-off
deployment, database recovery gates, production approval, and the existing
remote `deploy.sh` state machine.

## Decision

Use one private Tencent COS bucket as a temporary, immutable transfer relay.
The GitHub runner uploads the exact source and image bundles with a
repository-owned, serial multipart client whose individual HTTP requests have
exactly one attempt. A restricted server-side staging gate downloads them from the
same-region COS endpoint into a run-bound incoming directory, verifies every
identity, and never creates `releases-<SHA>` itself. Only the separately
approved production job may atomically promote a verified incoming directory
to `releases-<SHA>` and invoke `deploy.sh`.

The first external execution must use a new `artifact-stage-only` scope. It
proves upload, same-region download, receipt generation, and cleanup without
promotion, migration, application stop, image loading, or production deploy.

## Alternatives Rejected

### TCR as the immediate transport

TCR would give digest-addressed image pulls and layer reuse, but it changes the
reviewed archive-based deployment model and still needs a separate source
transfer. It remains a future optimization after the COS path is proven.

### Tencent-region self-hosted GitHub runner

An in-region runner would remove the slow path, but it expands the trusted code
execution surface next to production and requires runner lifecycle hardening.
That is disproportionate to the current transfer-only defect.

### Chunked SSH or a longer workflow timeout

Chunking could resume the existing path, but it does not fix the measured data
rate. Increasing the timeout cannot make a roughly 35-hour transfer fit the
GitHub-hosted runner execution ceiling. Neither approach is an acceptable
production data plane.

## Non-goals

- No provider, W5, publish, delivery, token smoke, or media generation call.
- No change to image contents, Dockerfiles, scan policies, SBOM generation, or
  the `deploy.sh` backup, restore, migration, routing, and rollback state
  machine.
- No bucket, CAM identity, GitHub Environment, server account, or live transfer
  is created by the local implementation gate.
- No automatic retry of a failed artifact stage or production deployment.
- No claim that a local fixture, COS upload, or `artifact-stage-only` run is a
  production application deployment.

## Workflow Scopes and Job Graph

`workflow_dispatch.inputs.execution_scope` gains one value:

- `archive-only`: current local runner archive evidence only;
- `remote-dry-run`: archive plus the restricted source rsync dry-run;
- `artifact-stage-only`: remote dry-run plus COS upload, same-region download,
  verification, receipt, and incoming cleanup;
- `deploy`: all prior gates, COS staging, production approval, atomic promotion,
  and the existing remote deployment.

For `artifact-stage-only` and `deploy`, the ordering is fixed:

1. exact-main provenance;
2. backend/frontend preflight;
3. three exact images, runtime smoke, three SBOMs, three Grype scans, three
   Trivy scans, unified High/Critical enforcement, and exact release archive;
4. restricted remote source dry-run;
5. `production-artifact-staging` Environment approval;
6. start one runner-monotonic 1,800-second transfer deadline, bind one exact
   regional COS endpoint and bucket, then perform COS upload and immutable
   object verification;
7. server-side bandwidth probe, incoming download, identity verification, and
   transfer receipt;
8. for `artifact-stage-only`, delete the verified incoming directory and stop;
9. for `deploy`, wait for the existing `production` Environment approval,
   revalidate the incoming receipt, atomically promote it, then invoke the
   unchanged provider-off `deploy.sh`.
10. if staging, its evidence upload, the deploy approval, or the deploy job
    fails after remote state may exist, request one exact cleanup of the
    unpromoted SHA/run/attempt/manifest transaction. The in-job EXIT handler
    attempts this first; a separate `production-artifact-staging` compensation
    job covers late stage-job and deploy-job failure. A promoted final path
    makes either cleanup fail closed instead of deleting it.

The stage job and production job must not use `always()` to bypass failed
prerequisites. Evidence-upload and cleanup steps may use `always()` but cannot
promote or deploy.

## Exact Transfer Identity

The build job produces these objects:

- `release-source-<SHA>.tar.gz` and adjacent SHA-256;
- `source-manifest.v1.json` with its SHA-256 recorded in the transfer manifest;
- `release-images-<SHA>.tar.gz` and adjacent SHA-256;
- `image-digests.txt` with exactly the backend, frontend, and rendering image
  IDs in canonical order;
- `release-transfer-manifest.v1.json`.

Before extracting the same-run GitHub release artifact, the stage job downloads
its raw ZIP through the Actions API, normalizes the producer
`artifact-digest`, and requires an exact SHA-256 match. A mismatch fails before
ZIP extraction, manifest creation, COS access, or any remote action; the digest
is an enforcement gate, not a value recorded without verification.

The source archive is built from the exact Git tree, not the mutable worktree.
The generated source manifest is included separately and binds the same
40-character revision. Gzip output uses a fixed timestamp mode. The transfer
manifest contains only bounded, non-secret facts:

- schema version;
- source revision, workflow run ID, and run attempt;
- GitHub release artifact ID and artifact digest;
- object key, byte size, and SHA-256 for both archives and both checksum files;
- the three ordered image IDs;
- one exact regional COS endpoint host in the form
  `cos.<region>.myqcloud.com` and one exact `<bucket>-<appid>` bucket name;
- creation and expiry timestamps;
- provider-off and forbidden-operation statements.

Each role has a fixed maximum download size: source archive 2 GiB, source
manifest 16 MiB, image archive 16 GiB, and detached checksum/digest files 256
bytes. A larger manifest claim fails before server download.

Canonical COS object keys are content-addressed:

```text
ai-video/releases/<SHA>/<archive-sha256>/release-source-<SHA>.tar.gz
ai-video/releases/<SHA>/<archive-sha256>/release-source-<SHA>.tar.gz.sha256
ai-video/releases/<SHA>/<archive-sha256>/source-manifest.v1.json
ai-video/releases/<SHA>/<archive-sha256>/release-images-<SHA>.tar.gz
ai-video/releases/<SHA>/<archive-sha256>/release-images-<SHA>.tar.gz.sha256
ai-video/releases/<SHA>/<archive-sha256>/image-digests.txt
ai-video/releases/<SHA>/<archive-sha256>/transactions/<run-id>/<attempt>/release-transfer-manifest.v1.json
```

Here `<archive-sha256>` is the exact image-archive SHA-256. It is the stable
transfer-prefix identity for the six shared immutable objects; it is not a
mutable upload ID or workflow run ID. Because the manifest itself binds the
workflow run, attempt, creation, and expiry, it uses a run-bound transaction
subkey below that content prefix. This avoids a create-only collision between
separately approved runs while keeping the large objects content-addressed.

Upload uses create-only object semantics. A new run always uploads a new
run-bound manifest. An existing shared object key may be reused only when the
operator explicitly selects `resume_transfer=true` in a newly approved run;
the runner first verifies signed-range total size plus immutable SHA-256/size
metadata, and the server later downloads and verifies the complete bytes before
accepting them. Otherwise any existing key fails the workflow.
Overwrite, mutable aliases, `latest`, branch names, and tag-only identities are
forbidden.

## COS Client and Credential Boundary

The workflow uses the repository-owned Python COS V5 signer and HTTP client in
`scripts/release_transfer.py`. It follows no redirects, performs no automatic
request retry, uploads serial 64 MiB parts, validates per-part MD5/ETag plus
whole-object SHA-256/size metadata, and aborts an incomplete multipart upload
once on failure. It never downloads or executes a mutable transfer binary.
Client or signing changes require reviewed code and behavior tests.

The private `production-artifact-staging` Environment contains exactly these
secret names:

- `COS_SECRET_ID`;
- `COS_SECRET_KEY`;
- `COS_SESSION_TOKEN`;
- `TRANSFER_HOST`;
- `TRANSFER_USER`;
- `TRANSFER_SSH_KEY`;
- `TRANSFER_KNOWN_HOSTS`.

It contains these non-secret variables:

- `COS_BUCKET`;
- `COS_ENDPOINT`;
- `TRANSFER_TARGET_DIR`.

The COS credential triple must be temporary STS material for the current
window. A long-lived CAM key is rejected by operational policy. Its CAM policy
is limited to `GetBucketVersioning` plus object operations in the one bucket
under `ai-video/releases/` and run-bound probe prefixes. The bucket must have
never enabled versioning; both `Enabled` and `Suspended` fail before the first
probe or release-object mutation because COS no-overwrite is ineffective for a
versioned bucket. The stage environment has the same main/tag branch policy and
administrator-bypass prohibition as production, but it cannot access
`DEPLOY_*` secrets.

Tag-triggered releases also pass through this Environment and the same COS
stage. A tag never bypasses either the staging approval or the production
approval.

Credentials remain only in GitHub's masked step environment and signer process
memory. Shell tracing is disabled. Secret values,
signed URLs, authorization headers, absolute runner paths, and COS session
tokens are forbidden from receipts and uploaded artifacts.

Every signed URL host must equal the exact host derived from the manifest,
`<bucket>.<endpoint-host>`. A different bucket, another valid COS region, a
generic `*.myqcloud.com` host, redirect, non-HTTPS scheme, or non-443 port is
rejected before download. The probe binds the same bucket and endpoint, and
the downloaded canonical manifest must hash to the receipt-bound manifest
SHA-256 before receipt readback, cleanup, or promotion can succeed.

The server receives signed GET URLs only over SSH standard input. A root-owned
wrapper captures the forced command before sudo, passes it as one non-shell
argument to an exact staging allowlist, and never preserves arbitrary caller
environment. URLs never appear in the SSH command, process arguments,
repository, GitHub output, or receipt. Every signed GET URL, including resume
readback, has an effective validity equal to the lesser
of the requested value and the remaining shared transfer deadline, never more
than 1,800 seconds; less than 60 seconds remaining fails before signing. The
gate retains URLs only in process memory.

## Multipart Upload and Explicit Resume

Before any full release-object upload, the runner starts one monotonic
1,800-second deadline and uploads a bounded 64 MiB
probe object exactly once. It gates the measured runner-to-COS upload leg,
then the restricted server downloads the same object and gates the
COS-to-Lighthouse leg. The code-owned gates for both legs are:

- measured throughput at least 2 MiB/s;
- estimated full-upload duration at most 1,800 seconds;
- exact probe size and SHA-256;
- exactly one attempt for each HTTP request and no redirect following.

Failure stops before server staging. Probe objects use a run-bound prefix and
are deleted after measurement; bucket lifecycle independently expires abandoned
probe and multipart data.

The same deadline covers bucket-state verification, both probe legs, every
shared-object readback/upload, manifest upload, signed-URL staging, and all
remote downloads plus their hashing, archive/source verification, and receipt
commit. Each socket timeout is capped by the remaining deadline; the runner
sends only the bounded remaining seconds to the server, which constructs its
own monotonic deadline. The probe, stage, and receipt SSH pipelines are also
bounded by the runner's remaining monotonic time, so SSH handshake delay
cannot grant a fresh server budget. HUP/INT/TERM and deadline expiry enter
the same bounded multipart abort, `.part`, incoming, and probe cleanup paths.
The server rejects any pre-existing probe receipt before download. Receipt and
incoming-directory mutations establish intent before the filesystem operation
and record the created inode while handled signals are blocked. If failure
occurs after committing this invocation's receipt or directory, cleanup only
removes the exact owned inode and canonical transaction state; a foreign race,
ownership ambiguity, or rollback failure is an explicit manual-recovery state
rather than an ordinary transfer failure.
The install-time cross-root atomic no-replace probe records its source inode;
cleanup may remove that inode from either side after a successful or ambiguous
rename, but must preserve any race-winning directory, file, or symlink and
report manual recovery.
Runner-local exclusive manifest writes use the same pre-effect signal boundary
and inode identity: interruption removes only the owned partial file, while a
cleanup double fault reports manual recovery and a pre-existing output is never
deleted. This occurs before COS mutation but remains part of the fail-closed
contract.
Server download `.part` creation also carries one intent through `O_EXCL`,
open/fstat, streaming, checksum callers, and outer probe cleanup. Cleanup can
unlink only the recorded regular owner/single-link inode; an open race is
preserved as a stable existing-destination failure, while an inode replacement
or cleanup double fault is preserved for explicit manual recovery.
The stage job has a 40-minute outer limit only to leave cleanup/evidence
headroom; it does not extend the 1,800-second transfer authority.

Full upload uses serial 64 MiB parts, Content-MD5 and returned ETags,
create-only completion, immutable SHA-256/size object metadata, and no
automatic HTTP retries. The never-versioned bucket check runs before every
transfer. Resume is never automatic. A later, explicitly authorized run
first performs a one-byte signed range readback for each of the six shared
objects. Exact total size and both immutable metadata fields must match the new
manifest; exact objects are reused, missing objects are uploaded create-only,
and any mismatch fails before that object is mutated. A complete six-object
readback is mandatory before the run-bound manifest upload. The client makes
one abort request after multipart failure; bucket lifecycle independently
removes any abandoned incomplete upload. There is no opaque local checkpoint
or implicit cross-run authority.

## Server Bandwidth Gate and Incoming Transaction

The staging SSH identity is distinct from the production deploy identity. Its
authorized key is restricted to one root-owned gate and cannot run an arbitrary
shell or arbitrary/mutating Docker, migration, backup, service, cron, nginx,
provider, publish, or delivery command. The only Docker operation in the gate
is a fixed read-only `docker ps` runtime-safety probe before cleanup/promotion.

Before creating incoming state, the gate downloads the full signed, run-bound
64 MiB probe object into a root-owned temporary file, verifies its fixed hash,
and deletes it. It requires at least 2 MiB/s and an estimated full-download
duration of at most 1,800 seconds. Failure emits only a bounded phase terminal
and does not create a candidate directory.

The probe request binds the exact COS regional endpoint and bucket. After
downloading only the bounded transfer manifest from their derived exact host,
the server requires both values to match and
recomputes the 1,800-second estimate from the manifest's complete seven-object
byte total before downloading any large release object; runner-supplied size is
only an earlier conservative precheck, never the acceptance authority.

The incoming path is under a root-owned `0700` staging root. The installer
first verifies a complete contract/gate/wrapper trio in a root-owned immutable
content-addressed version directory, then atomically replaces one fixed wrapper
symlink while holding a root-only install lock. A failed switch or final verify
restores the prior pointer, so concurrent forced commands observe only a
complete old or complete new trio. Install root, versions root and each runtime
must be non-symlink `root:root:0755`; the lock is `root:root:0600`, and these
facts are rechecked immediately before and after the pointer switch. The lock
is opened without symlink following or truncation and must be a single-link
regular inode. On failure the EXIT handler attempts pointer rollback and every candidate,
pointer, and previous temporary cleanup independently. Cleanup faults cannot
short-circuit later compensation or replace the original failure and add the
stable `release_transfer_gate_install_cleanup_failed` terminal.
If pointer rollback fails, the previous-pointer snapshot is retained for
manual recovery while candidate and pointer temporaries are still cleaned.
Every root Python helper runs isolated from cwd and environment; the installed
gate loads only its exact sibling contract. Candidate and
published runtime bytes are rehashed against the frozen content-address before
publication and immediately before the pointer switch. It also verifies this root and
`/opt/ai-video` are on the same filesystem:

```text
/var/lib/ai-video-release-transfer/.incoming-<SHA>-<run-id>-<run-attempt>/
```

It starts with a root-owned `0600` marker containing the exact manifest digest,
run identity, expected final path, and state `downloading`. Downloaded files
use `.part` suffixes. Each file is renamed only after size and SHA-256 match.
The source archive is inspected before extraction: absolute paths, parent
traversal, device nodes, FIFOs, unexpected members, any per-member size or
digest mismatch, and more than 2 GiB declared or extracted source bytes fail
closed. Every member and symlink target also has bounded UTF-8 bytes,
255-byte components, and at most 64 path components before any tree creation.
Setuid, setgid, sticky, or world-writable archive modes also fail.
Regular files are normalized to `0644` or `0755` from the reviewed executable
bit, and every directory to `0755`, independently of the root process umask.
The complete mode contract is re-read from the immutable source archive and
reverified both after extraction and immediately before promotion. Immediately
before promotion, every source regular-file byte, symlink target, exact file
set, exact directory set, and entry type is recomputed from
`source-manifest.v1.json` and the immutable source archive; only the fixed six
transfer artifacts, transfer manifest, receipt, and marker are excluded from
the source set. Extracted source and the source manifest must bind the exact
revision.
The image archive, adjacent checksum, and three image digests must match the
transfer manifest.

After all checks, the marker becomes `verified`. The staging gate cannot rename
the directory to `releases-<SHA>`, cannot run arbitrary or mutating Docker, and
cannot modify `current`; it may run only the fixed read-only `docker ps` safety
probe described above.

Promotion uses Linux `renameat2(RENAME_NOREPLACE)` to atomically rename that
directory to `/opt/ai-video/releases-<SHA>`. The installer performs a real
temporary no-replace rename across the configured staging and release roots,
so an `EXDEV`, unsupported primitive, or incompatible mount arrangement fails
configuration verification. The release root itself must remain a non-symlink
`root:root:0755` directory with stable device/inode identity; its identity and
mode are rechecked immediately before the irreversible rename. Immediately
before rename, the complete source
mode contract is reverified, the six manifest-bound transfer files become
root-owned `0644`, and the transaction root becomes `0755`, so the non-root
deploy user can read the immutable release; the marker and receipt stay
private. The receipt expiry is then checked again immediately adjacent to the
irreversible rename; expiry or preparation failure restores the incoming root
to `0700` and leaves its verified marker intact. If the post-rename
promoted-marker write fails,
the production gate first renames the final directory back to its exact
incoming path with the same no-replace primitive and restores the verified marker. A failed compensating rename
is reported as manual recovery, never as successful promotion.

For `artifact-stage-only`, the workflow reads back the verified receipt and
then asks the restricted gate to delete only that exact incoming directory.
Deletion requires all of these facts:

- valid marker and exact run/SHA/attempt;
- path matches the incoming grammar and is on the expected filesystem;
- path is not `current`, previous, or any `releases-*` directory;
- no process or container references it;
- `/proc/self/mountinfo` and every descendant device prove there is no nested
  mount or cross-filesystem boundary, followed by fd-relative/no-follow delete;
- final release path is absent.

For `deploy`, the separately approved production job repeats those checks,
requires marker state `verified`, atomically renames incoming to
`releases-<SHA>`, revalidates the final marker and archive checksum, and only
then invokes `deploy.sh`.

## Failure and Cancellation Semantics

Every stage has a stable terminal code. At minimum:

- `cos_versioning_gate_failed`;
- `runner_probe_failed`;
- `server_probe_failed`;
- `cos_release_upload_failed`;
- `cos_identity_readback_failed`;
- `cos_manifest_upload_failed`;
- `incoming_stage_failed`;
- `incoming_cleanup_failed`;
- `incoming_promotion_failed`;
- `cos_probe_cleanup_failed`;
- `transfer_passed`.

The remote gate emits a bounded `release-transfer-gate-terminal.v1` failure
object with an action-specific stable code. Only a fully verified stage writes
`release-transfer-receipt.v1.json`; the GitHub job reads it back and compares
the two canonical byte streams. Receipts contain state, identities, byte
counts, elapsed time, measured speed, expected duration, and timestamps. They do
not contain credentials, URLs, headers, raw exception text, or unbounded paths.

Bounded JSON readers reject malformed, oversized, or more than 64-level input
with stable phase terminals; a parser `RecursionError` never escapes as a
traceback. On normal failure, signal, or timeout, the gate removes temporary
credential files and `.part` files. The runner marks the exact probe key as a
possible mutation before issuing its single PUT, so an ambiguous response also
triggers one idempotent exact probe DELETE. That DELETE gets a fresh bounded
30-second cleanup deadline independent of an expired transfer deadline and is
never retried. Runner-side failure handling also
issues one idempotent cleanup for the exact run identity, covering a broken SSH
receipt stream after the server already reached `verified`, probe deletion
failure, or another late transfer-step error. A verified incoming directory is
retained only while an authorized deploy run awaits production approval. If
the stage job later fails while uploading evidence, or the deploy job does not
complete successfully, a separate `cleanup-staged-release` compensation job
uses only the staging identity and the exact artifact-stage manifest output.
It is eligible for failed as well as successful artifact-stage results once
that identity output exists. Its own terminal evidence is always uploaded. An
unverified directory is deleted when its marker is valid and
cleanup can be proven. If marker, path, ownership, filesystem, current-pointer,
process, container, or final-release state is ambiguous, cleanup stops, reports
failure, and requires manual recovery. It never guesses or recursively removes
a broad path.

GitHub cannot guarantee a new runner job after a whole-workflow cancellation,
and the staging Environment may require a fresh human approval for the
compensation job. A cancellation or rejected cleanup approval therefore keeps
the exact incoming transaction for the restricted manual `cleanup` command;
it is not represented as cleaned. The bucket lifecycle covers COS objects but
never authorizes deletion of a server incoming transaction.

Bucket lifecycle is a second safety net, not the primary cleanup mechanism:
probe objects, incomplete multipart uploads, and release objects expire under
separate reviewed retention periods. The workflow must not grant bucket-wide
delete authority merely to implement cleanup.

## Tests

### Static workflow contract

- The four scopes and exact job conditions/needs are fixed.
- Archive-only jobs contain no COS, transfer, production, SSH, or deployment
  secrets and no network mutation.
- Artifact staging cannot access `DEPLOY_*`; production deployment cannot
  access raw COS credentials.
- The repository COS signer, 64 MiB part size, exact-one-attempt request rule,
  never-versioned bucket gate, two-leg probe size, speed threshold, and maximum
  estimated duration are exact.
- Signed URLs are passed only over standard input and are absent from logs,
  outputs, artifacts, and receipts.
- Final promotion is ordered after verified receipt readback and production
  approval; remote deploy is ordered after promotion.
- A failed/rejected deploy schedules one exact staging-identity compensation;
  it has no COS or production secret, deletes no final release, always emits a
  bounded terminal artifact, and is absent for stage-only or successful deploy.
- Late artifact-stage/evidence failure with a published manifest output also
  schedules exact compensation; all such failures use the canonical
  `incoming_cleanup_failed` terminal rather than a generic cleanup label.
- One 1,800-second monotonic deadline is initialized once, propagated as
  remaining time, and precedes all release-object/probe/stage operations.

### Transfer unit and integration fixtures

- Canonical manifest and receipt generation is deterministic.
- Size, SHA, artifact digest, image-order, source-SHA, endpoint, object-prefix,
  expiry, and run-attempt mutations fail before transfer or promotion.
- Exact regional endpoint, bucket-derived URL host, canonical manifest-byte
  digest, hostile umask, unsafe source modes, deep JSON, signal, shared-deadline,
  and mixed/stale installer mutations fail closed.
- Slow probe, zero bytes, partial upload, multipart mismatch, expired STS,
  signed-URL expiry, range refusal, truncated download, checksum mismatch, tar
  traversal, invalid member type, source-manifest mismatch, and image-digest
  mismatch all fail closed.
- Resume reuses only exact shared objects after signed-range size/metadata
  readback, uploads only missing objects create-only, and never auto-resumes.
- Cancellation and double-failure paths leave production, `current`, Docker,
  database, cron, backup, nginx, providers, publish, and delivery untouched.
- Cleanup rejects malformed markers, symlinks, hard-link escapes, wrong owners,
  cross-filesystem paths, active processes, containers, current/previous/final
  releases, and any path outside the incoming grammar.
- Promotion is atomic, create-only, same-filesystem, and idempotently refuses an
  existing final path.

### Local evidence boundary

Local tests use fake COS and SSH endpoints or fixture clients. They may prove
logic and fail-closed behavior only. They do not prove COS account readiness,
real bandwidth, live server staging, migration, deployment, or production
acceptance.

## Rollout Gates

1. Local implementation, focused/expanded/full tests, lint, type checks, YAML
   parsing, action pinning, docs, diff, and secret scans.
2. Independent six-dimension review and repair loop until approved.
3. Exact-path local commit, push, PR review, and exact-head CI under separate
   authorization.
4. Merge and exact-main automatic CI under separate authorization.
5. Fresh exact-main `archive-only` under separate authorization.
6. Configure and read back the private COS bucket, lifecycle, STS policy,
   `production-artifact-staging` Environment, and restricted staging SSH gate
   under separate authorization.
7. Fresh exact-main `remote-dry-run` under separate authorization.
8. One `artifact-stage-only` live transfer with zero automatic retry. It must
   produce matching local/remote receipts and leave no incoming/final release.
9. Only after an independent review approves that receipt may a new, exact
   `execution_scope=deploy` authorization be requested.

## Evidence Labels

- Design and local fixtures: `L2 local/static/fixture`.
- COS account and staging-gate readback: `L4 authorized-live configuration`.
- Successful `artifact-stage-only`: `L4 authorized-live transfer`, not an
  application deployment.
- Production health observed without mutation: `L3 production read-only`.
- Successful provider-off deploy plus exact backup/restore/migration/runtime
  and public acceptance: `L4 authorized-live deployment` with an explicit L3
  application acceptance report.

No lower grade may be promoted to a higher claim without the corresponding new
evidence.
