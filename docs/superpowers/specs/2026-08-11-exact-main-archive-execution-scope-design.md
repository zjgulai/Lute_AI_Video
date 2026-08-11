---
title: "Exact-main release archive execution scopes"
doc_type: design
module: ci-cd
topic: exact-main-archive-provenance
status: proposed
created: 2026-08-11
updated: 2026-08-11
owner: self
source: human+ai
---

# Exact-main Release Archive Execution Scopes

## Context

Pull-request CI validates the PR merge result. On a `pull_request` event,
`github.sha` is GitHub's synthetic merge revision rather than the PR head
revision. The resulting backend image is valid PR evidence, but it is not the
canonical deployable archive for the eventual `main` revision.

The canonical `.github/workflows/deploy.yml` already solves image identity and
packaging correctly: it accepts only a workflow revision equal to the current
`origin/main` tip, builds all three images, validates their revision and version
labels, performs provider-off runtime smoke, generates SBOM and scan evidence,
and uploads one checksummed `docker save` archive. Its current job graph then
always continues into the restricted remote dry-run and production deployment
paths. That makes it impossible to request only the exact-main archive without
also entering later external gates.

## Goals

1. Allow an authorized operator to generate an exact-main release archive and
   its evidence without contacting a remote host or entering a production
   Environment.
2. Preserve the existing exact-main provenance requirement for every manual
   execution scope.
3. Preserve the existing remote dry-run and production deployment ordering.
4. Keep tag-triggered behavior unchanged.
5. Keep archive generation provider-off and independent from W5, publish, and
   delivery authority.

## Non-goals

- Generate a deployable archive from a PR head or synthetic PR merge revision.
- Merge a PR, change branch protection, or configure GitHub Environments.
- Push images to a registry or change the existing `docker save` archive
  format.
- Add a second release workflow or duplicate the build-images implementation.
- Trigger a remote dry-run, deployment, provider job, W5 submit, publish, or
  delivery operation.

## Decision

Add a required `workflow_dispatch` choice input named `execution_scope` with
exactly these values:

- `archive-only` — run exact-main provenance, preflight, and `build-images`,
  then stop successfully.
- `remote-dry-run` — additionally run the restricted remote rsync dry-run, then
  stop successfully without entering the production Environment.
- `deploy` — preserve the complete current path through remote dry-run and the
  production deployment Environment.

The manual default is `archive-only`. A tag push has no dispatch input and
retains the existing effective scope `deploy`.

## Workflow Contract

| Trigger | Effective scope | Exact-main provenance | Preflight | Build/archive | Remote dry-run | Production deploy |
|---|---|---:|---:|---:|---:|---:|
| `workflow_dispatch` | `archive-only` | required | required | required | skipped | skipped |
| `workflow_dispatch` | `remote-dry-run` | required | required | required | required | skipped |
| `workflow_dispatch` | `deploy` | required | required | required | required | required |
| `push` tag `v*.*.*` | `deploy` | required | required | required | required | required |

The `provenance` job continues to fetch `refs/heads/main` and requires exactly
one result whose 40-character revision equals `github.sha`. Selecting another
branch in the manual workflow UI therefore fails before build or external
access.

The `remote-dry-run` job receives a job-level condition equivalent to:

```yaml
github.event_name != 'workflow_dispatch' ||
inputs.execution_scope == 'remote-dry-run' ||
inputs.execution_scope == 'deploy'
```

The `deploy` job receives a job-level condition equivalent to:

```yaml
github.event_name != 'workflow_dispatch' ||
inputs.execution_scope == 'deploy'
```

Existing `needs` relationships remain unchanged. A failed provenance,
preflight, build, scan, checksum, or remote dry-run prevents downstream work.
The new conditions only skip work beyond the selected successful boundary;
they never convert a failed dependency into success.

## Archive and Provenance Contract

`archive-only` reuses the existing `build-images` job without changing its
contents or artifact format. The successful artifact remains:

```text
release-bundle-<exact-main-sha>/
  release-images-<exact-main-sha>.tar.gz
  release-images-<exact-main-sha>.tar.gz.sha256
  image-digests.txt
  sbom-backend.spdx.json
  sbom-frontend.spdx.json
  sbom-rendering.spdx.json
  scan-backend.json
  scan-frontend.json
  scan-rendering.json
```

Identity remains bound by all existing controls:

- workflow revision equals the current `origin/main` tip;
- all three image tags contain the exact main SHA;
- all three OCI revision labels equal that SHA;
- all three OCI version labels equal the semantic version authority;
- runtime smoke runs against the same loaded images that are scanned and
  packaged;
- the archive has an adjacent SHA-256 checksum;
- image IDs, SBOMs, and scanner JSON are uploaded in the same 14-day artifact.

An `archive-only` success supports the claim "exact-main L2 release archive and
CI evidence are available." It does not support claims of remote readiness,
production deployment, production health, provider readiness, or publish and
delivery capability.

## Security and Failure Behavior

- `archive-only` must not declare or enter either GitHub Environment.
- It must not reference `DRY_RUN_*` or `DEPLOY_*` secrets.
- It must not make SSH or rsync calls.
- It retains `RUN_TOKEN_SMOKE=0` and does not construct a provider-authorized
  execution path.
- Unknown manual values cannot be submitted because the input is a required
  GitHub Actions choice. Static regression tests also lock the exact option set
  and default.
- Scanner failure evidence is uploaded before the workflow fails closed, as in
  the current build contract. Failed scans never produce a release bundle.
- A successful archive-only run leaves `remote-dry-run` and `deploy` visibly
  skipped, not failed.

## Files and Responsibilities

- `.github/workflows/deploy.yml` — define the manual execution scope and gate
  the two external jobs without changing build/archive behavior.
- `tests/test_deploy_workflow.py` — lock the exact option set, default, tag
  compatibility, job conditions, dependency ordering, and secret isolation.
- `docs/runbooks/github-actions-deploy-secrets.md` — document all three manual
  scopes, their authority boundaries, and expected job outcomes.

No application, database, provider, deployment script, Dockerfile, dependency,
or production configuration file changes are required.

## Verification Strategy

1. Add failing YAML contract tests for the required choice input, exact options,
   `archive-only` default, job conditions, and unchanged `needs` graph.
2. Add negative assertions proving `archive-only` does not require either
   Environment or any SSH/deploy secret.
3. Apply the minimal workflow change and make the focused tests pass.
4. Run the complete deployment-workflow and workflow-governance regression
   suite, YAML parsing, Ruff, and diff/secret checks.
5. Run an independent six-dimension read-only review covering requirements,
   logic, edge cases, code quality, tests, and executable workflow semantics.
6. Only after a separately authorized commit, push, merge, and exact-main
   `archive-only` dispatch may GitHub evidence be promoted from local L2 to
   exact-main CI archive evidence.

## Rollout Gates

1. **Local design gate:** this specification is reviewed and approved.
2. **Local implementation gate:** workflow, tests, and runbook pass focused and
   expanded provider-off verification plus independent review.
3. **Git gate:** exact files are separately authorized for stage, commit, and
   push to the existing PR branch.
4. **PR gate:** PR checks pass; the PR remains Draft until separately promoted.
5. **Merge gate:** merge is separately authorized and `main` identity is read
   back from GitHub.
6. **Archive gate:** manually dispatch `execution_scope=archive-only` against
   exact `main`; verify the artifact name, archive checksum, image IDs, SBOMs,
   scans, revision labels, and skipped external jobs.
7. **External gates:** remote dry-run and production deploy retain their own
   distinct authorizations and are not implied by archive success.

## Acceptance Criteria

- The manual workflow exposes exactly the three approved scopes and defaults to
  `archive-only`.
- Exact-main provenance, preflight, build, smoke, SBOM, scan, packaging, and
  checksum behavior are unchanged for every scope.
- `archive-only` completes successfully with both external jobs skipped.
- `remote-dry-run` cannot reach production deploy.
- `deploy` and valid tag pushes retain the existing full ordered path.
- Failed prerequisites remain fail-closed.
- Focused and expanded tests pass and independent review reports
  `accepted_actionable_findings=0`.
- No merge, workflow dispatch, remote access, production mutation, provider
  call, W5 submit, publish, or delivery occurs during local implementation.
