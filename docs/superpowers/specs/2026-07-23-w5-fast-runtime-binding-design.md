# W5 Fast Runtime Binding Design

## Status

Approved for provider-off implementation. This design does not authorize a
provider call, production deployment, publish, or delivery.

## Problem

The completed W5-04 readiness slice proves that a private activation record is
bound to one canonical Fast plan. It does not bind that approval to the exact
HTTP request or idempotency key, does not consume the activation durably, and
does not inject the approved total budget into the provider-cost account.
Allowing `/fast/submit` to execute from readiness alone would therefore permit
request drift or reuse of one approval.

## Decision

Add a second private record, `w5-fast-runtime-binding.v1`, generated from:

- the canonical W5 Fast plan;
- the validated activation record, including a SHA-256 over its complete
  canonical content rather than only its logical ID;
- the exact credential-free Fast request and effective generation policy;
- the SHA-256 of the one raw `Idempotency-Key`;
- the expected provider/model/runtime envelope.

The runtime binding stores hashes and bounded identifiers only. It never stores
the raw idempotency key, provider key, or prompt.

Production activation is opt-in through three server-owned private paths. All
three paths absent preserves the existing route. Any partial configuration
fails closed. When enabled, every `/fast/submit` request must match the private
binding before a new durable claim may be created.

The server compares the bound provider/model/runtime envelope with the actual
server-owned Fast routing configuration before it consumes the activation.
LLM provider/model or video provider/model/resolution drift is a binding
mismatch, not an execution-time fallback.

## Exact initial Fast envelope

- scenario: `fast`
- artifact disposition: `pending_review`
- provider mutation retry cap: `0`
- submission cap: `1`
- required job categories: one `llm` and one `video`
- optional `tts`: allowed only when both plan and request select it
- video provider/model: `poyo` / `seedance-2`
- video resolution: `720p`
- duration: the exact normalized 10- or 15-second request value
- LLM provider/model: `deepseek` / `deepseek-v4-flash`
- publish and delivery authority: false

## Durable one-shot rule

`idempotency_records` gains a nullable trusted authorization reference. A
partial unique index on `(tenant_id, trusted_authorization_ref)` applies when
the reference is present. The initial W5 owner claim persists the activation
ID in the same atomic insert as the idempotency record.

- same tenant + same raw key + same request + same activation is read-only
  replay;
- a different request on the same key is an idempotency conflict;
- a different key using the consumed activation is an activation-consumed
  conflict;
- initialization/provider/artifact failure never releases or restores the
  activation;
- stale nonterminal work remains `recovery_required` and is never resubmitted.

Replay of an already-consumed record is resolved from its durable key,
fingerprint, operation, scenario, and persisted authorization truth before the
current private packet is loaded. It remains available after the packet is
removed, rotated, malformed, or expired. Expiry and current private-packet
validation are required only before a new owner claim.

## Budget authority

Add a provider-neutral validated plan-budget authority beside the existing
single-provider authority. Both share the exact fields required by provider
account initialization. For W5 Fast:

- authorization reference is the activation ID;
- total cap is the exact plan budget;
- account cap is the minimum of the server cap and plan cap;
- the durable provider-cost ledger remains the aggregate spend stop-loss;
- request fields can never supply or increase the budget.

The runtime binding separately enforces exact provider job categories and the
code-owned Fast operation vocabulary.

## Failure and evidence boundaries

Stable client-visible failures reveal only bounded codes:

- `w5_fast_binding_unavailable`
- `w5_fast_binding_invalid`
- `w5_fast_binding_mismatch`
- `w5_fast_activation_expired`
- `w5_fast_activation_consumed`

No error contains a private path, prompt, raw key, credential, provider
response, or exception text. A provider-off test may prove request binding,
atomic consumption, replay, and budget projection. Only a separately approved
and logged production call may be labelled L4.
