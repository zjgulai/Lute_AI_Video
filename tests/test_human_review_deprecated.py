"""Pin /pipeline/{thread_id}/review/{review_node} as a no-op in StepRunner mode.

P1-3 in NEXT-STEPS-2026-05-11.md asked us to verify the three HITL audit-review
branches (APPROVED / CHANGES_REQUESTED / REJECTED) work end-to-end in
production. Sprint 1 investigation found the path is **dead code** under
the StepRunner-driven architecture in v0.2.x:

  - submit_review (src/routers/pipeline.py) treats all actions as
    "idempotent_skip" and returns a deprecation message.
  - The real review-style HITL is Gate candidate selection
    (/scenario/{s}/gate/{label}/{gate_id}/approve), exercised by
    GatePanel.tsx in the frontend.
  - The audit_reports + AUTO_APPROVE_THRESHOLD path in src/graph/routing.py
    only runs inside the LangGraph proxy, which P4-4 made best-effort.

These tests pin the no-op behavior so future drift (someone wiring the
endpoint up again without removing the deprecation banner) is caught.
If real HITL audit-review behavior is ever restored, update the
NEXT-STEPS P1-3 entry + delete this file.
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize("action_value", ["approve", "reject", "request_changes"])
async def test_submit_review_returns_idempotent_skip(action_value):
    """All three HITL actions return status='idempotent_skip' with a message
    pointing at the Gate candidate-approval endpoint as the live alternative."""
    from src.routers._state import ReviewAction
    from src.routers.pipeline import submit_review

    resp = await submit_review(
        thread_id="thread_test",
        review_node="strategy_audit",
        action=ReviewAction(action=action_value, reviewer_notes=""),
    )
    assert resp["status"] == "idempotent_skip"
    assert resp["thread_id"] == "thread_test"
    assert resp["review_node"] == "strategy_audit"
    assert resp["action"] == action_value
    assert "gate" in resp["message"].lower()
    assert "/scenario/" in resp["message"]


@pytest.mark.asyncio
async def test_submit_review_unknown_action_still_no_ops():
    """Unknown action value should still get the no-op response, not crash."""
    from src.routers._state import ReviewAction
    from src.routers.pipeline import submit_review

    resp = await submit_review(
        thread_id="thread_x",
        review_node="script_audit",
        action=ReviewAction(action="garbled", reviewer_notes=""),
    )
    assert resp["status"] == "idempotent_skip"
    assert resp["action"] == "garbled"
