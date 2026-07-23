# W3 Reproducibility, Observability, and Disaster-Recovery Closure Plan

**Scope:** Local-only closure for W3-01–W3-07 and W3-09–W3-11. W3-08, W3-12,
W3-13, and W3-17 remain external authorization/evidence gates. No GitHub update,
production mutation, provider call, publish, delivery, notification, bucket/KMS
operation, or infrastructure reload is allowed.

**Completion truth:** Every behavior change starts with a failing contract and receives
the smallest compatible implementation. Each sub-batch passes focused and expanded
local gates, then the existing independent read-only six-dimension reviewer verifies
requirements, logic, edge cases, code quality, test coverage, and actual results. The
main thread fixes accepted findings and the same reviewer repeats until `PASS / APPROVE`
or a concrete blocker remains.

## Batch E1 — Runtime and dependency reproducibility (W3-01–W3-04)

### Task 1 — One production interpreter and dependency SSOT (W3-01/W3-02)

**RED:** contracts must fail while Docker uses Python 3.14, CI mixes 3.11/3.12,
Ruff/Pyright target 3.11, Docker installs ranged `requirements.txt`, and CI installs
unlocked editable dependencies. They must also fail if the production dependency set
omits `yt-dlp`, `faster-whisper`, `transformers`, `torch`, or Pillow.

**GREEN:** pin production and CI to CPython 3.12.13, set project/tool targets to 3.12,
and make `pyproject.toml` plus `uv.lock` the only dependency SSOT. Move every production
runtime dependency into `[project.dependencies]`; keep test/lint/type/audit tools in the
`dev` extra. Pin CPU-only torch to the explicit official PyTorch CPU index. Both backend
Dockerfiles use a digest-pinned Python base and version-pinned uv, then run locked
production sync; CI runs the same locked production set plus `dev`. Retain
`requirements.txt` only if a generated compatibility export is still required, with a
drift check and no Docker/CI authority.

The lock must be regenerated only through uv. A clean temporary environment must pass
critical imports and `/health` construction under Python 3.12.13 before the task closes.

### Task 2 — Vulnerability gates (W3-04)

**RED:** workflow contracts fail while Python and npm production trees have no blocking
audit step or while image Critical/High enforcement can disappear silently.

**GREEN:** add locked `pip-audit`, production-only npm audits for `web` and `rendering`,
and an exact image-scan contract that preserves the existing SBOM/Trivy release gate.
Any allowlist must be a reviewed, expiring record with package/CVE/reason/owner; no
blanket ignore or nonblocking success is permitted. Dependabot owner configuration stays
external and is reported separately.

### Task 3 — Real Pyright gate without suppression (W3-03)

**RED:** contracts fail when `make typecheck` is missing, CI omits it, execution
environments do not cover `src` and `tests`, a new diagnostic appears, or the command can
return success without running Pyright.

**GREEN:** configure Python 3.12 execution environments for production and tests. Remove
all trustworthy production `src` diagnostics, starting with repository row typing and
optional pool/connection control flow. Add a real `make typecheck` and CI gate. Historical
test diagnostics receive a checked-in exact diagnostic fingerprint ratchet: removed
diagnostics are allowed, any new diagnostic fails, and the baseline cannot be refreshed by
the check command. No ignore, suppression, rule downgrade, or fabricated zero-error claim.

### Task 4 — E1 verification and independent review

Run lock freshness, clean-environment imports, focused/full backend, Ruff, production
source Pyright, test ratchet, audit contracts, frontend/rendering npm gates, Docker build
contract, diff, docs governance, and secret scans. A real Docker build or online advisory
scan is separate evidence from a static workflow contract and must be reported honestly.
Then run the independent review/reverification loop.

**Closed locally 2026-07-22:** final backend `4122 passed`; source Pyright `0 errors` with
diagnostic/suppression/config ratchets; final locked image
`sha256:01b2e4bc18f59ba14032a696405ec0263c9cc5ff30add4b666fb26fff7a5e5c4` passed non-root,
offline-import, fail-closed media, and exact High/Critical scan gates. The same independent reviewer
returned `PASS / APPROVE` after three read-only correction cycles with
`accepted_actionable_findings=0`. GitHub/Dependabot and production evidence remain external.

## Batch E2 — Observable metrics and owned monitoring config (W3-05–W3-07)

### Task 5 — Canonical metrics and call-site truth (W3-05)

**RED:** query contracts fail for `status="error"`, `step_name`, or any metric/label/enum
not emitted by the registry. Tests reproduce S5 double counting and final-step degraded
runs being recorded as success. Retained zero-valued gauges must have real update paths.

**GREEN:** define one low-cardinality metric contract; add and wire HTTP request count and
latency using route templates and status classes; derive pipeline success only after final
lifecycle truth; emit each pipeline completion once; wire active background tasks and
provider failure facts or remove unsupported rule/panel families. Update all rules and
dashboard targets to the exact exported names, labels, and enum values.

Completion emission uses one server-owned durable claim. PostgreSQL performs a conditional
JSONB update, SQLite uses a write transaction, and filesystem-only mode uses a per-label
cross-process lock. Concurrent finalizers must produce one winner and one metric emission;
the durable business lifecycle remains authoritative if a process crashes after claim and
before the in-memory Prometheus increment.

### Task 6 — promtool and semantic query contracts (W3-06)

Add a version/digest-pinned `promtool check rules` plus `promtool test rules` lane. Every
alert must have non-firing, firing, and resolved fixtures, and the fixture alert-name set
must exactly equal the rule set. A Python contract validates every rule/dashboard metric,
label matcher, and enum against the registry, including histogram derived series; deleting
an exporter family must make the test red.

### Task 7 — Repository-owned monitoring boundary (W3-07)

Choose repository-managed local configuration because no verifiable external scrape or
receiver contract exists. Add secret-free Prometheus scrape/rule config, Alertmanager
template, Grafana datasource/dashboard provisioning, and a monitoring compose profile or
overlay. The local profile uses only internal networking and fixture receiver configuration.
Close the current public `/metrics` contract drift locally by defining the exact protected
production boundary; applying nginx/network changes remains a deployment authorization.

### Task 8 — E2 verification and independent review

Run focused telemetry/pipeline/background-task tests, all monitoring contracts, promtool,
compose config, affected/full backend, Ruff/Pyright, diff/docs/secret gates, then the same
review loop. W3-08 remains blocked until a separately authorized real firing and resolved
notification drill succeeds.

## Batch E3 — Exact recovery identity and off-host abstraction (W3-09–W3-11)

### Task 9 — Restore-set fail-closed repair (W3-09)

**RED:** before any write, restore must reject target-extra, target-missing, stats/dump
set mismatch, duplicate/unknown table, and FK-cycle cases. The verifier must reject any
target business table absent from the backup even when its row count would be zero.

**GREEN:** use dynamic public base-table discovery on both sides and require exact set
equality with the validated stats/dump. Remove fixed table counts/sets from the DR runbook
and governance tests.

### Task 10 — Versioned canonical backup manifest (W3-10)

Create strict `backup-manifest.v1.json` plus detached SHA-256. It records Git SHA,
deterministic source-manifest hash, immutable backend image digest/ID and OCI revision,
Alembic head, PostgreSQL server/client facts, per-table and total rows, media exact file
set/count/bytes/checksums, and every backup artifact checksum. Backup validates it before
atomic publish; restore validates the same schema before any write. Missing or inconsistent
Git/source/image/OCI facts fail closed. `manifest.txt` may remain only as a compatibility
summary.

### Task 11 — Off-host protocol and fake store (W3-11)

Implement a narrow create-only object-store protocol with `put`, `head/readback`, and
`download` receipts containing version ID, checksum, and encryption metadata. Dry-run
validates the local canonical manifest and builds a redacted plan without constructing a
client/transport. Fake-store tests cover duplicate keys, checksum drift, absent version or
encryption facts, ambiguous upload/readback, and secret-safe logging. Do not choose a real
provider, add credentials, upload, implement custom cryptography, or claim W3-12.

### Task 12 — E3 verification and independent review

Run focused backup/restore/off-host tests, shell syntax, disposable PostgreSQL 18
dump/restore/parity, mock media exact-set recovery, deploy-state contracts, affected/full
backend, Ruff/Pyright, diff/docs/secret gates, then the same review loop. W3-12 and W3-13
remain blocked until bucket/KMS/retention authority and an independent host-loss drill exist.

## External evidence boundary

- W3-08: one authorized firing and one resolved notification, exact receiver and window.
- W3-12: versioned immutable bucket, KMS, retention, least-privilege identities, real receipt.
- W3-13: independent host unavailable, off-host version restore, PG/media parity and RPO/RTO.
- W3-17: GitHub Environment secrets/protection and restricted remote dry-run.
- Deployment of this branch remains blocked because the canonical wrapper requires reviewed
  `origin/main`; no rsync or mutable-source substitute is allowed.
