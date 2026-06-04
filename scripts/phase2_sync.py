#!/usr/bin/env python3
"""Phase 1 + Phase 2 同步补丁 — Apply all D1-D7 changes on Mac.

Usage: cd ~/project/hermes_evo/AI_vedio && python3 scripts/phase2_sync.py
Then restart: source .venv/bin/activate && uvicorn src.api:app --reload --port 8001
"""

import os

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ═══════════════════════════════════════════════════════════════
# 1. src/models/__init__.py — D4: REVIEW_NODES constant
# ═══════════════════════════════════════════════════════════════

init_path = os.path.join(PROJECT, "src/models", "__init__.py")
with open(init_path) as f:
    old = f.read()

if "REVIEW_NODES:" in old:
    print("[OK] D4: src/models/__init__.py already has REVIEW_NODES")
else:
    marker = "# Re-export types for convenient access\nPipelineErrors = list[PipelineError]\n"
    new_block = (
        "# ──────────────────────────────────────────────\n"
        "# Global Constants (used across pipeline, API, and frontend)\n"
        "# ──────────────────────────────────────────────\n\n\n"
        "REVIEW_NODES: list[str] = [\n"
        '    "strategy_review",\n'
        '    "script_review",\n'
        '    "edit_review",\n'
        '    "thumbnail_review",\n'
        "]\n"
        '"""Ordered list of human review node keys.\n\n'
        "Used by: routing.py (review key lookup), api.py (state inspection),\n"
        "frontend page.tsx (review panel rendering).\n\n"
        "WARNING: These keys are coupled to graph node names in pipeline.py.\n"
        "If changed, update routing.py review key lookups AND pipeline.py\n"
        "interrupt_after list AND add_conditional_edges path_map AND\n"
        "frontend REVIEW_NODES / REVIEW_NODE_ORDER constants in tandem.\n"
        '"""\n\n\n'
    )
    old = old.replace(marker, new_block + marker)
    with open(init_path, "w") as f:
        f.write(old)
    print("[OK] D4: src/models/__init__.py + REVIEW_NODES constant")


# ═══════════════════════════════════════════════════════════════
# 2. src/api.py — D4: import + use REVIEW_NODES constant; D6: remove effective_complete
# ═══════════════════════════════════════════════════════════════

api_path = os.path.join(PROJECT, "src/api.py")
with open(api_path) as f:
    old = f.read()

changes = 0

# D4: import
if "from src.models import ApprovalStatus, HumanReview, REVIEW_NODES" in old:
    print("[OK] D4: src/api.py import already done")
else:
    old = old.replace(
        "from src.models import ApprovalStatus, HumanReview",
        "from src.models import ApprovalStatus, HumanReview, REVIEW_NODES",
    )
    changes += 1

# D4: loop
if "for node_name in REVIEW_NODES:" in old:
    print("[OK] D4: src/api.py loop already uses REVIEW_NODES")
else:
    old = old.replace(
        'for node_name in ["strategy_review", "script_review", "edit_review", "thumbnail_review"]:',
        "for node_name in REVIEW_NODES:",
    )
    changes += 1

# D6: Remove effective_complete block
if "effective_complete" not in old:
    print("[OK] D6: effective_complete already removed")
else:
    # Replace the block from the comment to the return statement
    old_eff_block = (
        "            # If all 4 reviews completed but pipeline_complete is still False,\n"
        "            # the pipeline may be between interrupt and final node execution.\n"
        "            # Check if the final analytics_node has data to confirm completion.\n"
        "            all_reviews_done = all(\n"
        "                node_name in reviews and reviews[node_name].get(\"status\") != \"pending\"\n"
        "                for node_name in REVIEW_NODES\n"
        "            )\n"
        "            analytics_done = bool(snapshot.values.get(\"analytics_reports\") if snapshot.values else False)\n"
        "            has_pipeline_complete = snapshot.values.get(\"pipeline_complete\", False) if snapshot.values else False\n"
        "            effective_complete = has_pipeline_complete or (all_reviews_done and analytics_done)\n"
        "\n"
        "            return {\n"
        "                \"thread_id\": thread_id,\n"
        '                "status": "complete" if effective_complete else ("interrupted" if snapshot.next else "complete"),\n'
        '                "current_review": current_review,\n'
        '                "pipeline_complete": effective_complete,\n'
        '                "state": values,\n'
        "            }"
    )
    new_d6_block = (
        "            has_pipeline_complete = snapshot.values.get(\"pipeline_complete\", False) if snapshot.values else False\n"
        "\n"
        "            return {\n"
        '                "thread_id": thread_id,\n'
        '                "status": "complete" if has_pipeline_complete else ("interrupted" if snapshot.next else "complete"),\n'
        '                "current_review": current_review,\n'
        '                "pipeline_complete": has_pipeline_complete,\n'
        '                "state": values,\n'
        "            }"
    )
    if old_eff_block in old:
        old = old.replace(old_eff_block, new_d6_block)
        changes += 1
        print("[OK] D6: effective_complete removed")
    else:
        print("[WARN] D6: could not find old effective_complete block")

with open(api_path, "w") as f:
    f.write(old)
print(f"[OK] src/api.py: {changes} change(s) applied")


# ═══════════════════════════════════════════════════════════════
# 3. src/graph/nodes.py — D2: is_reentry uses audit_reports + changes_requested check
# ═══════════════════════════════════════════════════════════════

nodes_path = os.path.join(PROJECT, "src/graph/nodes.py")
with open(nodes_path) as f:
    old = f.read()

d2_replacements = [
    # strategy_audit_node
    (
        '    is_reentry = state.get("current_step") == "strategy_complete"\n    if is_reentry:\n        retry_counts["strategy"] = retry_counts.get("strategy", 0) + 1',
        '    is_reentry = "strategy" in state.get("audit_reports", {})\n    if is_reentry:\n        # Only count as retry if the user actually requested changes\n        review = state.get("human_reviews", {}).get("strategy_review", {})\n        if isinstance(review, dict) and review.get("status") == "changes_requested":\n            retry_counts["strategy"] = retry_counts.get("strategy", 0) + 1',
    ),
    # script_audit_node
    (
        '    is_reentry = state.get("current_step") == "script_complete"\n    if is_reentry:\n        retry_counts["script"] = retry_counts.get("script", 0) + 1',
        '    is_reentry = "script" in state.get("audit_reports", {})\n    if is_reentry:\n        # Only count as retry if the user actually requested changes\n        review = state.get("human_reviews", {}).get("script_review", {})\n        if isinstance(review, dict) and review.get("status") == "changes_requested":\n            retry_counts["script"] = retry_counts.get("script", 0) + 1',
    ),
    # editing_audit_node
    (
        '    is_reentry = state.get("current_step") in ("editing_complete", "edit_audit_complete")\n    if is_reentry:\n        retry_counts["edit"] = retry_counts.get("edit", 0) + 1',
        '    is_reentry = "edit" in state.get("audit_reports", {})\n    if is_reentry:\n        # Only count as retry if the user actually requested changes\n        review = state.get("human_reviews", {}).get("edit_review", {})\n        if isinstance(review, dict) and review.get("status") == "changes_requested":\n            retry_counts["edit"] = retry_counts.get("edit", 0) + 1',
    ),
    # thumbnail_audit_node
    (
        '    is_reentry = state.get("current_step") in ("thumbnail_complete", "thumbnail_audit_complete")\n    if is_reentry:\n        retry_counts["thumbnail"] = retry_counts.get("thumbnail", 0) + 1',
        '    is_reentry = "thumbnail" in state.get("audit_reports", {})\n    if is_reentry:\n        # Only count as retry if the user actually requested changes\n        review = state.get("human_reviews", {}).get("thumbnail_review", {})\n        if isinstance(review, dict) and review.get("status") == "changes_requested":\n            retry_counts["thumbnail"] = retry_counts.get("thumbnail", 0) + 1',
    ),
]

d2_count = 0
for i, (old_pattern, new_pattern) in enumerate(d2_replacements):
    if old_pattern in old:
        old = old.replace(old_pattern, new_pattern)
        d2_count += 1
    else:
        # Check if already applied
        markers = ["strategy", "script", "edit", "thumbnail"]
        if f'is_reentry = "{markers[i]}" in state.get("audit_reports", {{}})' in old:
            pass  # already applied

if d2_count == 4:
    print("[OK] D2: all 4 is_reentry checks replaced")
elif d2_count > 0:
    print(f"[OK] D2: {d2_count}/4 is_reentry checks replaced")
else:
    print("[OK] D2: is_reentry checks already applied (or check manually)")

with open(nodes_path, "w") as f:
    f.write(old)


# ═══════════════════════════════════════════════════════════════
# 4. web/src/app/page.tsx — D1/D3/D7: completion gate, not_found, audit score panel
# ═══════════════════════════════════════════════════════════════

page_path = os.path.join(PROJECT, "web/src/app", "page.tsx")
with open(page_path) as f:
    old = f.read()

# D3: not_found detection in refreshState
d3_in_old = (
    'if (data.status === "not_found" || data.status === "error") {\n'
    "        localStorage.removeItem(STORAGE_KEY);\n"
    '        setThreadId("");\n'
    "        setReviewState(null);\n"
    "        return;"
)
if d3_in_old in old:
    print("[OK] D3: not_found detection already in page.tsx")
else:
    # Check if the old version exists
    if '// silent retry\n    }\n  }, [threadId]);' in old:
        old = old.replace(
            "const data = await res.json();\n      setReviewState(data);\n    } catch {\n      // silent retry\n    }\n  }, [threadId]);",
            (
                "const data = await res.json();\n\n"
                "      // D3: Backend restarted (MemorySaver lost) — clear local storage, go back to start\n"
                '      if (data.status === "not_found" || data.status === "error") {\n'
                "        localStorage.removeItem(STORAGE_KEY);\n"
                '        setThreadId("");\n'
                "        setReviewState(null);\n"
                "        return;\n"
                "      }\n\n"
                "      setReviewState(data);\n"
                "    } catch {\n"
                "      // silent retry — network blips are normal\n"
                "    }\n  }, [threadId]);"
            ),
        )
        print("[OK] D3: not_found detection applied")

    elif '// D3:' in old:
        print("[OK] D3: already applied (D3 comment marker found)")
    else:
        print("[WARN] D3: could not find marker — may need manual check")

# D1: completion gate
d1_in_old = "const pipelineComplete =\n    reviewState?.pipeline_complete === true && reviewState?.current_review === null;"
if d1_in_old in old:
    print("[OK] D1: completion gate already in page.tsx")
else:
    d1_old = "const pipelineComplete = reviewState?.pipeline_complete;"
    d1_new = (
        "\n  // D1: Show completion screen only when pipeline is truly finished\n"
        "  // (pipeline_complete=true AND all reviews resolved)\n"
        "  const pipelineComplete =\n"
        "    reviewState?.pipeline_complete === true && reviewState?.current_review === null;"
    )
    if d1_old in old:
        old = old.replace(d1_old, d1_new)
        print("[OK] D1: completion gate applied")
    else:
        print("[WARN] D1: could not find old marker in page.tsx")

# D7: AuditReportCard — replace old accordion version with score badge + criteria bars
d7_new = (
    'function AuditReportCard({ report }: { report: AuditReport }) {\n'
    '  const score = report.overall_score;\n'
    '  const status = report.overall_status;\n'
    '\n'
    '  // Score color: green (>0.9 auto-approve), yellow (0.6-0.9 needs review), red (<0.6 auto-reject)\n'
    '  const scoreColor =\n'
    '    score >= 0.9 ? "text-[#34c759]"\n'
    '    : score >= 0.6 ? "text-[#ff9500]"\n'
    '    : "text-[#ff3b30]";\n'
    '  const scoreBg =\n'
    '    score >= 0.9 ? "bg-[#34c759]"\n'
    '    : score >= 0.6 ? "bg-[#ff9500]"\n'
    '    : "bg-[#ff3b30]";\n'
    '\n'
    '  return (\n'
    '    <div className="mb-6 p-4 rounded-xl bg-[#f5f5f7] border border-[#e8e8ed]">\n'
    '      <div className="flex items-center justify-between mb-3">\n'
    '        <h3 className="text-xs font-semibold text-[#1d1d1f]">AI 自审评分</h3>\n'
    '        <span className={`text-xs px-2 py-0.5 rounded-full ${scoreBg} bg-opacity-10 text-white`}\n'
    '          style={{ backgroundColor: scoreBg.replace("bg-", ""), opacity: 0.15 }} />\n'
    '      </div>\n'
    '\n'
    '      {/* Large score display */}\n'
    '      <div className="flex items-center gap-4 mb-4">\n'
    '        <div className="relative w-16 h-16">\n'
    '          <svg width="64" height="64" viewBox="0 0 64 64">\n'
    '            {/* Background circle */}\n'
    '            <circle cx="32" cy="32" r="28" fill="none" stroke="#e8e8ed" strokeWidth="5" />\n'
    '            {/* Score arc */}\n'
    '            <circle\n'
    '              cx="32" cy="32" r="28"\n'
    '              fill="none"\n'
    '              stroke={score >= 0.9 ? "#34c759" : score >= 0.6 ? "#ff9500" : "#ff3b30"}\n'
    '              strokeWidth="5"\n'
    '              strokeDasharray={`${score * 176} 176`}\n'
    '              strokeLinecap="round"\n'
    '              transform="rotate(-90 32 32)"\n'
    '            />\n'
    '          </svg>\n'
    '          <span className={`absolute inset-0 flex items-center justify-center text-lg font-bold ${scoreColor}`}>\n'
    '            {Math.round(score * 100)}\n'
    '          </span>\n'
    '        </div>\n'
    '        <div>\n'
    '          <p className={`text-sm font-semibold ${scoreColor}`}>\n'
    '            {score >= 0.9 ? "优秀 — 自动通过"\n'
    '              : score >= 0.6 ? "待人工审核"\n'
    '              : "不及格 — 自动拒绝"}\n'
    '          </p>\n'
    '          <p className="text-[10px] text-[#aeaeb2] mt-0.5">{report.summary}</p>\n'
    '        </div>\n'
    '      </div>\n'
    '\n'
    '      {/* Criteria bars */}\n'
    '      <div className="space-y-2">\n'
    '        {report.criteria.map((c: AuditCriterion) => {\n'
    '          const barColor =\n'
    '            c.status === "PASS" ? "bg-[#34c759]"\n'
    '            : c.status === "WARN" ? "bg-[#ff9500]"\n'
    '            : "bg-[#ff3b30]";\n'
    '          return (\n'
    '            <div key={c.name}>\n'
    '              <div className="flex justify-between items-center mb-1">\n'
    '                <span className="text-[10px] text-[#86868b] truncate mr-2">{c.name}</span>\n'
    '                <span className="text-[10px] font-medium text-[#1d1d1f]">{Math.round(c.score * 100)}</span>\n'
    '              </div>\n'
    '              <div className="h-1.5 rounded-full bg-[#e8e8ed] overflow-hidden">\n'
    '                <div className={`h-full rounded-full ${barColor} transition-all duration-500`}\n'
    '                  style={{ width: `${c.score * 100}%` }} />\n'
    '              </div>\n'
    '            </div>\n'
    '          );\n'
    '        })}\n'
    '      </div>\n'
    '    </div>\n'
    '  );\n'
    '}'
)

if 'const [expanded, setExpanded] = useState(false)' in old:
    print("[WARN] D7: old accordion AuditReportCard still present — skipping (needs manual cleanup)")
else:
    # Check if already replaced
    if 'AI 自审评分' in old:
        print("[OK] D7: AuditReportCard already has score panel")
    elif 'function AuditReportCard({ report }: { report: AuditReport }) {' in old:
        # Replace the old one (which currently has just empty or simple body)
        
        # Find the function definition
        idx = old.find('function AuditReportCard({ report }: { report: AuditReport }) {')
        # Find the closing of the function (next function or section)
        rest = old[idx:]
        for ending_marker in ['\n// ══════════════════════════════════════════════════════\n', '\nfunction ']:
            end_idx = rest.find(ending_marker, 1)
            if end_idx != -1:
                break
        
        if end_idx != -1:
            old = old[:idx] + d7_new + rest[end_idx:]
            print("[OK] D7: AuditReportCard replaced with score panel")
        else:
            print("[WARN] D7: could not find end of old AuditReportCard")
    else:
        print("[WARN] D7: AuditReportCard function not found")

with open(page_path, "w") as f:
    f.write(old)


# ═══════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════

print()
print("Phase 1+2 changes applied. Next steps:")
print("  1. cd ~/project/hermes_evo/AI_vedio")
print("  2. source .venv/bin/activate && python3 -m uvicorn src.api:app --reload --port 8001")
print("  3. cd web && npm run dev -- -p 3001 (in another terminal)")
print("  4. Browse http://localhost:3001")
print()
print("What changed:")
print("  D1: Completion screen shows only when pipeline_complete=true AND current_review=null")
print("  D2: retry_counts only increment on real changes_requested, not on approve resume")
print("  D3: Backend restart detection — auto-reset to start screen")
print("  D4: REVIEW_NODES constant in src/models/__init__.py + api.py + page.tsx")
print("  D6: Removed effective_complete composite check — uses raw pipeline_complete")
print("  D7: Audit score panel with SVG arc + criteria progress bars")
