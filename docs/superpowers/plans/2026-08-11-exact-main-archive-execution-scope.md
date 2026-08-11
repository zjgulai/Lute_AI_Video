# Exact-main Archive Execution Scope Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an exact-main `archive-only` GitHub Actions path that builds and uploads the existing release bundle without entering remote dry-run or production deployment gates.

**Architecture:** Extend the existing `Deploy to Production` workflow with one required manual choice input. Keep provenance, preflight, image build, smoke, SBOM, scan, packaging, and artifact upload unchanged; use job-level conditions only at the two external boundaries. Lock the state machine with static YAML regression tests and document the operator-visible outcomes.

**Tech Stack:** GitHub Actions YAML, PyYAML, pytest, Markdown runbooks, existing Docker Buildx/SBOM/Grype/release-bundle pipeline.

## Global Constraints

- The approved design authority is `docs/superpowers/specs/2026-08-11-exact-main-archive-execution-scope-design.md`, SHA-256 `1d3c7e32b5cc36dd57419f3a37aaf9a22257ba20bd744d4237c704dfb2665ed0`.
- Manual scopes are exactly `archive-only`, `remote-dry-run`, and `deploy`; the default is exactly `archive-only`.
- Every scope retains `github.sha == origin/main` provenance, existing concurrency, preflight, build, smoke, SBOM, scan, archive, checksum, and 14-day retention behavior.
- Tag pushes retain the existing full remote-dry-run and deploy path.
- `archive-only` must not enter a GitHub Environment, read `DRY_RUN_*` or `DEPLOY_*`, execute SSH/rsync, deploy, or invoke provider/W5/publish/delivery behavior.
- Do not modify application code, database code, Dockerfiles, dependency files, deployment scripts, Environment settings, or branch protection.
- Preserve the unrelated untracked `scripts/space_governance.py`; never stage, delete, or edit it.
- Stage, commit, push, merge, workflow dispatch, remote access, and deployment each require their separately named authorization. When authorization is absent, stop at a reviewed local candidate.

---

## File Map

- Modify `.github/workflows/deploy.yml`: define the manual execution scope and gate only `remote-dry-run` and `deploy`.
- Modify `tests/test_deploy_workflow.py`: specify the exact input contract and job-state transition rules.
- Modify `docs/runbooks/github-actions-deploy-secrets.md`: document operator choices, evidence grade, credentials, and expected skipped jobs.
- Preserve `docs/superpowers/specs/2026-08-11-exact-main-archive-execution-scope-design.md`: approved design and evidence boundary.
- Preserve this plan as the executable checklist and review handoff.

### Task 1: Specify the execution-scope contract with failing tests

**Files:**
- Modify: `tests/test_deploy_workflow.py:21-40`
- Modify: `tests/test_deploy_workflow.py:85-100`
- Modify: `tests/test_deploy_workflow.py:768-788`

**Interfaces:**
- Consumes: the parsed `.github/workflows/deploy.yml` `workflow` fixture.
- Produces: exact constants `REMOTE_DRY_RUN_IF` and `DEPLOY_IF`, plus regression tests that later workflow edits must satisfy.

- [ ] **Step 1: Add the exact expression and runbook constants**

Add beside the existing path constants:

```python
GITHUB_ACTIONS_DEPLOY_RUNBOOK = (
    REPO_ROOT / "docs" / "runbooks" / "github-actions-deploy-secrets.md"
)
REMOTE_DRY_RUN_IF = (
    "${{ github.event_name != 'workflow_dispatch' || "
    "inputs.execution_scope == 'remote-dry-run' || "
    "inputs.execution_scope == 'deploy' }}"
)
DEPLOY_IF = (
    "${{ github.event_name != 'workflow_dispatch' || "
    "inputs.execution_scope == 'deploy' }}"
)
```

- [ ] **Step 2: Add the failing manual-input test**

Add to `TestDeployWorkflow` after `test_workflow_dispatch_requires_reason_input`:

```python
def test_workflow_dispatch_has_exact_execution_scope_choices(self, workflow):
    on = workflow.get(True) or workflow.get("on")
    dispatch = (on.get("workflow_dispatch") or {}).get("inputs") or {}
    execution_scope = dispatch.get("execution_scope") or {}

    assert execution_scope.get("required") is True
    assert execution_scope.get("type") == "choice"
    assert execution_scope.get("default") == "archive-only"
    assert execution_scope.get("options") == [
        "archive-only",
        "remote-dry-run",
        "deploy",
    ]
```

- [ ] **Step 3: Add the failing job-boundary test**

Add near the existing remote dry-run contract:

```python
def test_execution_scope_gates_only_external_jobs(self, workflow):
    jobs = workflow["jobs"]

    for job_name in ("provenance", "preflight", "build-images"):
        assert jobs[job_name].get("if") is None
        assert jobs[job_name].get("environment") is None

    assert jobs["remote-dry-run"].get("if") == REMOTE_DRY_RUN_IF
    assert jobs["deploy"].get("if") == DEPLOY_IF
    assert jobs["remote-dry-run"]["needs"] == [
        "provenance",
        "preflight",
        "build-images",
    ]
    assert jobs["deploy"]["needs"] == [
        "preflight",
        "build-images",
        "remote-dry-run",
    ]
```

- [ ] **Step 4: Run the two tests and prove RED**

Run:

```bash
uv run pytest -q \
  tests/test_deploy_workflow.py::TestDeployWorkflow::test_workflow_dispatch_has_exact_execution_scope_choices \
  tests/test_deploy_workflow.py::TestDeployWorkflow::test_execution_scope_gates_only_external_jobs
```

Expected: both tests fail because `execution_scope` and both job-level conditions do not exist.

- [ ] **Step 5: Inspect the failure scope**

Run:

```bash
git diff -- tests/test_deploy_workflow.py
git status --short --untracked-files=all
```

Expected: only the test file plus the already approved spec/plan and unrelated `scripts/space_governance.py` are uncommitted; no workflow behavior has changed yet.

### Task 2: Implement the minimal fail-closed workflow state machine

**Files:**
- Modify: `.github/workflows/deploy.yml:4-10`
- Modify: `.github/workflows/deploy.yml:387-390`
- Modify: `.github/workflows/deploy.yml:449-453`
- Test: `tests/test_deploy_workflow.py`

**Interfaces:**
- Consumes: `workflow_dispatch.inputs.execution_scope` or a non-dispatch tag event.
- Produces: exact job conditions consumed by the static tests and GitHub Actions scheduler.

- [ ] **Step 1: Add the required manual choice input**

Under the existing required `reason` input, add:

```yaml
      execution_scope:
        description: "Maximum authorized workflow boundary"
        required: true
        default: archive-only
        type: choice
        options:
          - archive-only
          - remote-dry-run
          - deploy
```

- [ ] **Step 2: Gate the remote dry-run job**

Add immediately below `remote-dry-run:` and before `name:`:

```yaml
    if: ${{ github.event_name != 'workflow_dispatch' || inputs.execution_scope == 'remote-dry-run' || inputs.execution_scope == 'deploy' }}
```

Do not change its `needs`, Environment, secrets, SSH, rsync, or artifact steps.

- [ ] **Step 3: Gate the deploy job**

Add immediately below `deploy:` and before `name:`:

```yaml
    if: ${{ github.event_name != 'workflow_dispatch' || inputs.execution_scope == 'deploy' }}
```

Do not add `always()` or alter `needs`; prerequisite failures must continue to skip downstream execution.

- [ ] **Step 4: Run the RED tests and prove GREEN**

Run the command from Task 1 Step 4.

Expected: `2 passed`.

- [ ] **Step 5: Run the complete workflow contract file**

Run:

```bash
uv run pytest -q tests/test_deploy_workflow.py
```

Expected: all tests pass, including exact-main provenance, pinned actions, secret isolation, archive packaging, remote dry-run ordering, and production Environment assertions.

### Task 3: Document the operator contract and lock it with tests

**Files:**
- Modify: `tests/test_deploy_workflow.py`
- Modify: `docs/runbooks/github-actions-deploy-secrets.md:15-73`

**Interfaces:**
- Consumes: the three exact values defined by the workflow.
- Produces: an operator-facing matrix that does not grant authority beyond the selected scope.

- [ ] **Step 1: Add the failing runbook contract test**

Add to `TestDeployWorkflow`:

```python
def test_deploy_runbook_documents_execution_scope_boundaries(self):
    text = GITHUB_ACTIONS_DEPLOY_RUNBOOK.read_text()

    for scope in ("archive-only", "remote-dry-run", "deploy"):
        assert f"`{scope}`" in text
    assert "默认选择 `archive-only`" in text
    assert "PR head" in text
    assert "exact `origin/main`" in text
    assert "不会进入任何 GitHub Environment" in text
    assert "不构成生产部署证据" in text
```

- [ ] **Step 2: Run the test and prove RED**

Run:

```bash
uv run pytest -q \
  tests/test_deploy_workflow.py::TestDeployWorkflow::test_deploy_runbook_documents_execution_scope_boundaries
```

Expected: fail because the runbook still describes a single always-deploying manual path.

- [ ] **Step 3: Update the runbook trigger section**

Replace the manual-trigger description with a table containing these exact semantics:

```markdown
| `execution_scope` | 最后执行的成功边界 | Environment / 凭据 |
|---|---|---|
| `archive-only` | exact-main preflight、三镜像 smoke/SBOM/scan、release bundle | 不会进入任何 GitHub Environment，不读取 `DRY_RUN_*`/`DEPLOY_*` |
| `remote-dry-run` | 上述 archive + 受限 rsync dry-run artifact | 仅 `production-read-only-dry-run` 与 `DRY_RUN_*` |
| `deploy` | 完整 remote dry-run + production deploy/health smoke | 远端 dry-run 成功后才进入 `production` |
```

State immediately below the table:

```markdown
手动触发默认选择 `archive-only`。所有范围都要求 workflow SHA 精确等于执行时的 exact `origin/main` tip；PR head 或 pull-request synthetic merge SHA 不能生成 canonical deployable archive。`archive-only` 成功只构成 exact-main L2 archive/CI 证据，不构成生产部署证据。
```

- [ ] **Step 4: Run the runbook test and full workflow tests**

Run:

```bash
uv run pytest -q tests/test_deploy_workflow.py
```

Expected: all tests pass.

### Task 4: Execute provider-off verification and freeze the local candidate

**Files:**
- Verify: `.github/workflows/deploy.yml`
- Verify: `tests/test_deploy_workflow.py`
- Verify: `docs/runbooks/github-actions-deploy-secrets.md`
- Verify: approved spec and this plan

**Interfaces:**
- Consumes: the complete local candidate.
- Produces: fresh L2 verification receipts and a canonical five-path content manifest; no GitHub or production side effect.

- [ ] **Step 1: Run expanded release-governance tests**

Run:

```bash
uv run pytest -q \
  tests/test_deploy_workflow.py \
  tests/test_backup_manifest.py \
  tests/test_docker_no_token_preflight.py \
  tests/test_w4_release_operations_governance.py
```

Expected: all selected tests pass.

- [ ] **Step 2: Run the full provider-off backend suite**

Run:

```bash
uv run pytest -q
```

Expected: no new failure. Existing intentional skips/deselections must be reported exactly rather than rewritten as passes.

- [ ] **Step 3: Run static quality gates**

Run:

```bash
uv run ruff check tests/test_deploy_workflow.py
uv run python -c 'import pathlib,yaml; yaml.safe_load(pathlib.Path(".github/workflows/deploy.yml").read_text())'
git diff --check -- \
  .github/workflows/deploy.yml \
  tests/test_deploy_workflow.py \
  docs/runbooks/github-actions-deploy-secrets.md \
  docs/superpowers/specs/2026-08-11-exact-main-archive-execution-scope-design.md \
  docs/superpowers/plans/2026-08-11-exact-main-archive-execution-scope.md
```

Expected: all commands exit zero.

- [ ] **Step 4: Run the scoped secret and authority scan**

Run:

```bash
git diff --unified=0 -- \
  .github/workflows/deploy.yml \
  tests/test_deploy_workflow.py \
  docs/runbooks/github-actions-deploy-secrets.md \
  docs/superpowers/specs/2026-08-11-exact-main-archive-execution-scope-design.md \
  docs/superpowers/plans/2026-08-11-exact-main-archive-execution-scope.md \
  | rg '^\+' \
  | rg -i '(sk-[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16}|BEGIN [A-Z ]*PRIVATE KEY|Bearer [A-Za-z0-9_-]{20,})'
```

Expected: `rg` finds no match. Treat exit code 1 as clean only for this final match command.

- [ ] **Step 5: Freeze the exact five-path candidate**

For each candidate path, record status, regular-file type, byte size, SHA-256, and path sorted bytewise; hash the resulting newline-delimited manifest with SHA-256. Confirm the only other worktree entry is `?? scripts/space_governance.py` and the index is empty.

### Task 5: Run the independent six-dimension review and repair loop

**Files:**
- Review all five candidate paths from Task 4.

**Interfaces:**
- Consumes: frozen candidate manifest and fresh verification receipts.
- Produces: severity-rated findings and either `PASS / APPROVE, accepted_actionable_findings=0` or a repair list returned to the main thread.

- [ ] **Step 1: Send the frozen candidate to the existing independent reviewer**

The reviewer is read-only and checks:

1. requirements completeness;
2. logic correctness for dispatch, tag, failure, and skipped-job states;
3. edge cases including non-main dispatch and failed prerequisites;
4. workflow/test/runbook quality;
5. regression coverage;
6. actual local test and executable YAML results.

- [ ] **Step 2: Repair accepted findings in the main thread**

For every accepted finding, add or strengthen a failing test first, apply the minimal fix, rerun the focused and affected expanded gates, and update the frozen manifest.

- [ ] **Step 3: Re-submit to the same reviewer**

Repeat Steps 1-2 until `accepted_actionable_findings=0` or report the precise external blocker. The reviewer must not edit code or Git state.

### Task 6: Preserve the separately authorized external gates

**Files:**
- Candidate paths: exactly the five files frozen in Task 4.

**Interfaces:**
- Consumes: independently approved local candidate.
- Produces only what a later exact authorization names; this task grants no authority by itself.

- [ ] **Step 1: Stop at local closure when Git authorization is absent**

Report the candidate manifest, verification receipts, review verdict, and the unchanged external boundary. Do not stage or commit.

- [ ] **Step 2: If separately authorized, stage only the five exact paths**

Run explicit `git add -- <five paths>`; never use `git add .`. Recompute staged hashes, run path-aware `git diff --cached --check`, and prove `scripts/space_governance.py` is not staged.

- [ ] **Step 3: If separately authorized, create one commit and push the existing PR branch**

Use a single commit message such as:

```text
feat(release): add exact-main archive-only gate
```

Push only `codex/p0-h10-w4-release-20260810`, confirm PR #114 points to the new SHA, and monitor CI without merging.

- [ ] **Step 4: Keep merge and archive dispatch separate**

Only after fresh explicit authorization may the PR be promoted/merged. Only after `main` identity is read back and separately authorized may `Deploy to Production` be manually dispatched with `execution_scope=archive-only`. Verify the resulting bundle, checksum, image IDs, SBOMs, scan JSON, revision labels, and that both external jobs are skipped.

## Self-review Receipt

- Spec coverage: every goal, non-goal, state transition, identity rule, security boundary, verification requirement, review loop, and external gate maps to Tasks 1-6.
- Placeholder scan: no placeholder, deferred implementation marker, or unspecified error-handling step remains.
- Interface consistency: the input name is always `execution_scope`; values and ordering are always `archive-only`, `remote-dry-run`, `deploy`; expressions use `REMOTE_DRY_RUN_IF` and `DEPLOY_IF` consistently.
- Scope: implementation changes exactly three existing behavior/test/runbook files; spec and plan are documentation evidence. No application or deployment-script refactor is included.
