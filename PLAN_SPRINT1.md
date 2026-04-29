# Enterprise Hardening — Sprint 1: CRITICAL Gaps + Self-Audit

## Mandate

Execute the top-4 CRITICAL gaps from the audit, in order:

1. **GAP-11**: Retry count limit — stop infinite retry loops
2. **GAP-2**: LangGraph checkpoint model registration — prevent future deserialization breakage
3. **GAP-5**: Timeout protection on all LLM/external API calls
4. **GAP-1**: Retry (+ backoff) on all external API clients (LLM, DALL-E, ElevenLabs, Remotion)

After each gap is closed, run a **self-audit proof**: a concrete, verifiable demonstration that the fix works and cannot regress. Either a test that would fail before the fix, or a runtime trace that proves the new behavior.

## Self-Audit Rules

- Every fix MUST produce a **verifiable proof** — a test that guards this behavior
- After all 4 gaps, run FULL regression (`python3 -m pytest tests/ -v --tb=short`)
- Record before/after test counts
