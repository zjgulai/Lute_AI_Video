---
title: Publish Connector Truth and Fail-Closed Operations
doc_type: runbook
module: backend
topic: publish-connector-truth
status: superseded
created: 2026-07-14
updated: 2026-07-14
owner: self
source: human+ai
---

# Publish Connector Truth and Fail-Closed Operations

## Scope

This is the historical W1-24 local baseline for TikTok/Shopify credential and
connector-result truth. It is not the current execution entrypoint for receipt,
protocol, preflight, or status behavior. Use
[Publish receipt and protocol calibration](./publish-receipt-protocol-calibration.md)
for the active W1-25 contract. Neither document authorizes a real connector or
status call, production deployment, live publish, delivery, retry, or
reconciliation.

## Publish outcome matrix

| Observation | Attempt state | Stable code | HTTP | Acceptance | Retry |
|---|---|---|---:|---|---|
| Pre-consume readiness false | no attempt | `publish_connector_not_ready` | 503 | unconsumed | allowed after credential repair |
| Credential lost after consume, zero outbound | `failed` | `publish_connector_not_ready_after_consume` | 502 | consumed | forbidden |
| Real explicit rejection | `failed` | `publish_connector_failed` | 502 | consumed | forbidden |
| Injected simulated result | `failed` | `publish_connector_simulated` | 502 | consumed | forbidden |
| Missing/malformed truth or uncertain mutation | `ambiguous` | `publish_outcome_ambiguous` | 502 | consumed | forbidden |
| Trusted `simulated=false`, `success=true` | `published` | none | 200 | consumed | forbidden |

## Distribution status

The W1-24 external connector-status behavior is superseded. W1-25 changed the
deprecated route to tenant-bound durable TikTok receipt readback only. It never
calls a connector or external status API, Shopify returns a stable 410, missing
exact receipt returns 404, and contradictory or malformed durable truth fails
closed with 503.

## Incident handling

Never replay a consumed attempt automatically. For `ambiguous`, reconcile manually against the platform before any new human acceptance is created. Never restore a consumed acceptance.

## Safe rollback

Before rolling back an application version, block publish mutations and distribution status at the gateway. Do not roll back to a version that can fabricate mock `published`. Keep routes blocked until a version satisfying this truth contract is deployed.

## Evidence boundary

W1-24 local tests used fixture credentials, injected connectors, fake
transports, and disposable PostgreSQL 18. W1-25 later added local protocol and
receipt proof, but neither wave proves credential validity, real platform
scopes, real receipt truth, production deployment, or live publish. Those
external claims remain W1-26.
