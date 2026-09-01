---
title: "Production Operations Entry Point"
doc_type: workflow
module: operations
topic: production-operations-entrypoint
status: stable
created: 2026-08-01
updated: 2026-08-01
owner: self
source: human+ai
---

# Production Operations Entry Point

This is the single current index for production operation ownership. It grants
no authority by itself. Every mutation still requires its own exact scope,
immutable candidate identity, recovery evidence and human approval.

- Canonical deployment: [Lighthouse production deployment](../workflows/deploy-lighthouse-stable.md)
- Canonical disaster recovery: [Hermes-Evo disaster recovery](../disaster_recovery_runbook.md)
- Canonical provider token smoke: [Production E2E token smoke](./production-e2e-token-smoke.md)
- Current release identity: [Current release](../release/current.md)
- Current closure backlog: [Current backlog](../backlog/current.md)

Deploy is permanently provider-off. Token smoke is a separate, exact,
single-window authority and is never implied by deployment. Backup/restore,
migration, deployment, provider execution, publish and delivery remain distinct
gates. Do not copy commands from documents marked historical.

The production host must provide dependency-free Python 3.9 or newer for the
repository-owned preflight and manifest utilities. Application and image code
remain pinned to CPython 3.12.14. `scripts/project_version.py --check` includes
a Python 3.9/3.10 fallback and must pass before any release mutation.
