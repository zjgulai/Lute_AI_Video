---
title: "Current Release Identity"
doc_type: knowledge
module: release-governance
topic: current-release-identity
status: active
created: 2026-08-01
updated: 2026-08-01
owner: self
source: human+ai
semantic_version: "2.0.0"
---

# Current Release Identity

The semantic product version is `2.0.0`, sourced from `pyproject.toml` and
checked against frontend, lockfile and documentation projections by
`scripts/project_version.py --check`.

The expected external release tag is `v2.0.0`, but that tag does not currently
exist and this local batch is not authorized to create it. Semantic version is
not deployment identity: every release image and health response must also bind
the exact 40-character source revision. Production remains on its separately
verified deployed SHA until an authorized exact-image deployment succeeds.
