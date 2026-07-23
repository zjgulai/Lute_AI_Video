---
title: "W2-10-W2-13 State Parity, Quality Rewind, and Key Isolation Plan"
doc_type: workflow
module: pipeline
topic: state-rewind-key-isolation
status: stable
created: 2026-07-22
updated: 2026-07-23
owner: self
source: human+ai
---

# W2-10–W2-13 State Parity, Quality Rewind, and Key Isolation Plan

**Scope:** Local/disposable-only closure for canonical scenario state projection, filesystem/
SQLite/PostgreSQL 18 parity, bounded quality-feedback rewind, and request-scoped provider-key
isolation. No provider mutation, production change, GitHub update, publish, or delivery is allowed.

**Completion truth:** Focused and full tests, real disposable PostgreSQL 18 parity, static/security
gates, and the same independent six-dimension review loop must pass. Tests use fake transports or
constructor-only inspection; no provider client may send a request.

## Task 1 — Canonical state/API contract (W2-10)

**RED:** machine contract and generic scenario status must preserve `regenerate_chain` and
`soft_degraded_reasons` for filesystem, repository, live state, and durable result snapshots.
Missing/wrong-type values fail closed or normalize only at an explicitly documented legacy edge.

**GREEN:** extend the existing scenario-state contract/defaults and status projection without a
new endpoint or compatibility alias. Keep credentials and provider execution context out of state.

## Task 2 — Cross-backend parity (W2-11)

**RED:** one canonical nonterminal state with lifecycle/config/steps/gates/errors/regeneration and
soft-degradation facts must round-trip byte-equivalent JSON semantics through filesystem, real
SQLite, fake PG row, and guarded disposable PostgreSQL 18. Restart/load must preserve cursor and
tenant ownership.

**GREEN:** repair only projection/decoding fields proven missing. Do not add application-side DDL;
the existing columns and reviewed bootstrap/migration gates remain authoritative.

## Task 3 — Bounded quality rewind state machine (W2-12)

**RED:** when a consumer requests upstream regeneration, the current `resume()` call must stop;
direct consumer execution is forbidden until the exact upstream step successfully reruns; restart
preserves the pending rewind; after upstream success the consumer may run exactly once; attempts
above the fixed bound fail closed without another provider-capable epoch.

**GREEN:** persist one small rewind envelope inside canonical `config`, keep `regenerate_chain` as
append-only audit, and enforce cursor/transition guards in `StepRunner`. Do not infer success from a
pending status or skip the upstream execution.

## Task 4 — Request-scoped provider-key isolation (W2-13)

**RED:** two concurrent tenant contexts with distinct fake keys construct every active/retained
provider adapter with only their own key; no constructor creates HTTP transport; context reset
cannot retain the other tenant's key. Explicit server-owned injection remains deterministic and
legacy paid paths remain blocked.

**GREEN:** reuse the existing ContextVar resolver and fix only clients that bypass or mis-prioritize
it. Global environment remains a server fallback only when no request-scoped value exists. Never
persist, log, snapshot, or echo any key.

## Task 5 — Integration and independent review

Run state/status/quality/provider-isolation focused tests, real SQLite and disposable PG18 parity,
canonical S1–S5 hermetic regression, full backend, frontend/OpenAPI only if contracts change, Ruff,
target Pyright, diff and current-change secret scans. Send the complete Batch C diff to the existing
read-only reviewer across requirements, logic, edge cases, quality, coverage, and actual results;
fix and reverify until `PASS / APPROVE` or a concrete blocker.

**External boundary:** Remote CI and new-code deployment remain blocked while GitHub updates are
forbidden. Local success must not be described as production or provider evidence.
