#!/usr/bin/env python3
"""
在 Mac 上应用 routing.py 和 pipeline.py 的修复补丁。

用法：
    cd ~/project/hermes_evo/AI_vedio
    python3 scripts/apply_fix_patch.py

然后重启 uvicorn（Ctrl+C 再启动）。
"""

import os
import sys

BASE = os.path.dirname(os.path.dirname(__file__))

# ──────────────────────────────────────
# Patch 1: routing.py
#   Change priority: human_review FIRST, audit_guard SECOND
# ──────────────────────────────────────

ROUTING_PATH = os.path.join(BASE, "src", "graph", "routing.py")

ROUTING_OLD = '''def route_after_strategy(state: VideoPipelineState) -> str:
    """After strategy produces briefs → check audit then human review.

    Priority order:
      1. Audit-driven: high score → auto-approve, low score → reject
      2. Retry guard: exhausted retries → force-approve
      3. Human review: normal approval workflow
    """
    # Check audit score first
    audit_verdict = _audit_guard(state, "strategy")
    if audit_verdict == "approved":
        return "script_node"
    if audit_verdict == "rejected":
        return "__end__"

    # Then check retry guard
    override = _retry_guard(state, "strategy")
    review = state.get("human_reviews", {}).get("strategy_review")
    status = override or _get_approval_status(review)
    if status == "approved":
        return "script_node"
    if status == "changes_requested":
        return "strategy_node"
    return "strategy_node"'''

ROUTING_NEW = '''def route_after_strategy(state: VideoPipelineState) -> str:
    """After strategy produces briefs → check audit then human review.

    Priority order:
      1. Human review: explicit rejection or changes-requested overrides auto-approve
      2. Retry guard: exhausted retries → force-approve (prevents infinite loops)
      3. Audit-driven: high score → auto-approve, low score → reject, middle → re-loop
      4. Default: re-loop to strategy_node
    """
    # Check human review FIRST — explicit user action overrides auto decisions
    review = state.get("human_reviews", {}).get("strategy_review")
    override = _retry_guard(state, "strategy")
    user_status = override or _get_approval_status(review)
    if user_status == "approved":
        return "script_node"
    if user_status == "rejected":
        return "__end__"
    if user_status == "changes_requested":
        return "strategy_node"

    # No human review yet — fall through to audit-driven auto decisions
    audit_verdict = _audit_guard(state, "strategy")
    if audit_verdict == "approved":
        return "script_node"
    if audit_verdict == "rejected":
        return "__end__"

    # Middle ground: needs human review
    return "strategy_node"'''

# ──────────────────────────────────────
# Patch 2: pipeline.py
#   Add "__end__": END to all 4 conditional edge path_maps
# ──────────────────────────────────────

PIPELINE_PATH = os.path.join(BASE, "src", "graph", "pipeline.py")

PIPELINE_PATCHES = [
    # strategy_audit_node
    (
        '{"script_node": "script_node", "strategy_node": "strategy_node"}',
        '{"script_node": "script_node", "strategy_node": "strategy_node", "__end__": END}',
    ),
    # script_audit_node
    (
        '{"compliance_node": "compliance_node", "script_node": "script_node"}',
        '{"compliance_node": "compliance_node", "script_node": "script_node", "__end__": END}',
    ),
    # editing_audit_node
    (
        '{"audio_node": "audio_node", "editing_node": "editing_node"}',
        '{"audio_node": "audio_node", "editing_node": "editing_node", "__end__": END}',
    ),
    # thumbnail_audit_node
    (
        '{"distribution_node": "distribution_node", "thumbnail_node": "thumbnail_node"}',
        '{"distribution_node": "distribution_node", "thumbnail_node": "thumbnail_node", "__end__": END}',
    ),
]

def patch_file(path, old, new, label):
    if not os.path.exists(path):
        print(f"  SKIP {label}: {path} not found")
        return False
    with open(path) as f:
        content = f.read()
    if old not in content:
        print(f"  SKIP {label}: pattern not found (may already be patched)")
        return False
    content = content.replace(old, new, 1)
    with open(path, "w") as f:
        f.write(content)
    print(f"  PATCHED {label}")
    return True

if __name__ == "__main__":
    print("Applying fixes...")
    
    patched_any = False
    
    # Patch routing.py
    patched_any |= patch_file(ROUTING_PATH, ROUTING_OLD, ROUTING_NEW, "routing.py (route_after_strategy)") or \
                   patch_file(ROUTING_PATH, ROUTING_NEW, ROUTING_NEW, "routing.py (route_after_strategy)")
    
    # Patch route_after_script (same pattern)
    SCRIPT_OLD = '''    # Check human review FIRST
    audit_verdict = _audit_guard(state, "script")
    if audit_verdict == "approved":
        return "compliance_node"
    if audit_verdict == "rejected":
        return "__end__"'''
    
    SCRIPT_NEW = '''    # Check human review FIRST
    review = state.get("human_reviews", {}).get("script_review")
    override = _retry_guard(state, "script")
    user_status = override or _get_approval_status(review)
    if user_status == "approved":
        return "compliance_node"
    if user_status == "rejected":
        return "__end__"
    if user_status == "changes_requested":
        return "script_node"

    # No human review yet — fall through to audit-driven auto decisions
    audit_verdict = _audit_guard(state, "script")
    if audit_verdict == "approved":
        return "compliance_node"
    if audit_verdict == "rejected":
        return "__end__"'''
       
    patched_any |= patch_file(ROUTING_PATH, SCRIPT_OLD, SCRIPT_NEW, "routing.py (route_after_script)")
    
    # Same for editing
    EDIT_OLD = '''    # Check human review FIRST
    audit_verdict = _audit_guard(state, "edit")
    if audit_verdict == "approved":
        return "audio_node"
    if audit_verdict == "rejected":
        return "__end__"'''
    
    EDIT_NEW = '''    # Check human review FIRST
    review = state.get("human_reviews", {}).get("edit_review")
    override = _retry_guard(state, "edit")
    user_status = override or _get_approval_status(review)
    if user_status == "approved":
        return "audio_node"
    if user_status == "rejected":
        return "__end__"
    if user_status == "changes_requested":
        return "editing_node"

    # No human review yet — fall through to audit-driven auto decisions
    audit_verdict = _audit_guard(state, "edit")
    if audit_verdict == "approved":
        return "audio_node"
    if audit_verdict == "rejected":
        return "__end__"'''
    
    patched_any |= patch_file(ROUTING_PATH, EDIT_OLD, EDIT_NEW, "routing.py (route_after_editing)")
    
    # Same for thumbnail
    THUMB_OLD = '''    # Check human review FIRST
    audit_verdict = _audit_guard(state, "thumbnail")
    if audit_verdict == "approved":
        return "distribution_node"
    if audit_verdict == "rejected":
        return "__end__"'''
    
    THUMB_NEW = '''    # Check human review FIRST
    review = state.get("human_reviews", {}).get("thumbnail_review")
    override = _retry_guard(state, "thumbnail")
    user_status = override or _get_approval_status(review)
    if user_status == "approved":
        return "distribution_node"
    if user_status == "rejected":
        return "__end__"
    if user_status == "changes_requested":
        return "thumbnail_node"

    # No human review yet — fall through to audit-driven auto decisions
    audit_verdict = _audit_guard(state, "thumbnail")
    if audit_verdict == "approved":
        return "distribution_node"
    if audit_verdict == "rejected":
        return "__end__"'''
    
    patched_any |= patch_file(ROUTING_PATH, THUMB_OLD, THUMB_NEW, "routing.py (route_after_thumbnail)")
    
    # Patch pipeline.py — add __end__ to all 4 conditional edges
    if os.path.exists(PIPELINE_PATH):
        with open(PIPELINE_PATH) as f:
            content = f.read()
        for old, new in PIPELINE_PATCHES:
            if old in content:
                content = content.replace(old, new, 1)
                print(f"  PATCHED pipeline.py: {old}")
                patched_any = True
            else:
                print(f"  SKIP pipeline.py: {old} (already patched)")
        with open(PIPELINE_PATH, "w") as f:
            f.write(content)
    
    print()
    if patched_any:
        print("Done. Restart uvicorn (Ctrl+C then re-run) to pick up changes.")
        print("  source .venv/bin/activate && python3 -m uvicorn src.api:app --reload --port 8001")
    else:
        print("Nothing to patch — all fixes appear to be already applied.")
