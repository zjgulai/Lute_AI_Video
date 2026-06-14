#!/usr/bin/env python3
"""Phase 1 同步补丁 — Apply all D1/D3/D4 changes on Mac.

Usage: cd ~/project/hermes_evo/AI_vedio && python3 scripts/phase1_sync.py
Then restart: source .venv/bin/activate && uvicorn src.api:app --reload --port 8001
"""

import os

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ═══════════════════════════════════════════════
# D4: src/models/__init__.py — add REVIEW_NODES constant
# ═══════════════════════════════════════════════

init_path = os.path.join(PROJECT, "src/models", "__init__.py")
with open(init_path) as f:
    old = f.read()

if "REVIEW_NODES:" in old:
    print("[OK] D4 already applied: src/models/__init__.py")
else:
    marker = "# Re-export types for convenient access\nPipelineErrors = list[PipelineError]\n"
    new = old.replace(
        marker,
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
        '"""\n\n\n' + marker,
    )
    with open(init_path, "w") as f:
        f.write(new)
    print("[OK] D4 applied: src/models/__init__.py + REVIEW_NODES constant")


# ═══════════════════════════════════════════════
# D4: src/api.py — use REVIEW_NODES constant
# ═══════════════════════════════════════════════

api_path = os.path.join(PROJECT, "src/api.py")
with open(api_path) as f:
    old = f.read()

if "from src.models import ApprovalStatus, HumanReview, REVIEW_NODES" in old:
    print("[OK] D4 already applied: src/api.py (import)")
else:
    old_import = "from src.models import ApprovalStatus, HumanReview"
    new_import = "from src.models import ApprovalStatus, HumanReview, REVIEW_NODES"
    old = old.replace(old_import, new_import)
    with open(api_path, "w") as f:
        f.write(old)
    print("[OK] D4 applied: src/api.py (import)")

# Replace hardcoded lists
changes = 0
# Strategy review list
old_loop = 'for node_name in ["strategy_review", "script_review", "edit_review", "thumbnail_review"]:'
new_loop = "for node_name in REVIEW_NODES:"
if old_loop in old:
    old = old.replace(old_loop, new_loop)
    changes += 1

# all_reviews_done list
old_all = (
    'all(\n                node_name in reviews and reviews[node_name].get("status") != "pending"\n'
    '                for node_name in ["strategy_review", "script_review", "edit_review", "thumbnail_review"]\n'
    "            )"
)
new_all = (
    'all(\n                node_name in reviews and reviews[node_name].get("status") != "pending"\n'
    "                for node_name in REVIEW_NODES\n"
    "            )"
)
if old_all in old:
    old = old.replace(old_all, new_all)
    changes += 1

# Fix duplicate comment
old_dup = "            # Determine current review node\n            # Determine current review node"
if old_dup in old:
    old = old.replace(old_dup, "            # Determine current review node")

# Restore the reviews = ... line if it was accidentally there
if 'reviews = snapshot.values.get("human_reviews", {}) if snapshot.values else {}' not in old:
    # Find where to insert
    old = old.replace(
        "            current_review = None\n            for node_name in REVIEW_NODES:",
        '            current_review = None\n            reviews = snapshot.values.get("human_reviews", {}) if snapshot.values else {}\n            for node_name in REVIEW_NODES:',
    )

with open(api_path, "w") as f:
    f.write(old)
print(f"[OK] D4 applied: src/api.py ({changes} list replacement(s))")


# ═══════════════════════════════════════════════
# D1 + D3: web/src/app/page.tsx — completion gate + not_found handling
# ═══════════════════════════════════════════════

page_path = os.path.join(PROJECT, "web/src/app", "page.tsx")
with open(page_path) as f:
    old = f.read()

# D3: Update refreshState to detect not_found
d3_marker = "const data = await res.json();\n\n      setReviewState(data);"
d3_new = (
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
    "    }"
)
d3_simple_marker = "const data = await res.json();\n      setReviewState(data);\n    } catch {\n      // silent retry\n    }"
if d3_simple_marker in old:
    old = old.replace(d3_simple_marker, d3_new)
    print("[OK] D3 applied: page.tsx (not_found detection)")
elif d3_marker in old:
    old = old.replace(d3_marker, d3_new)
    print("[OK] D3 applied: page.tsx (not_found detection)")
else:
    print("[WARN] D3: could not find marker in page.tsx — check file")

# D1: Completion gate — pipeline_complete true AND current_review null
d1_old = "const pipelineComplete = reviewState?.pipeline_complete;"
d1_new = (
    "\n  // D1: Show completion screen only when pipeline is truly finished\n"
    "  // (pipeline_complete=true AND all reviews resolved)\n"
    "  const pipelineComplete =\n"
    "    reviewState?.pipeline_complete === true && reviewState?.current_review === null;"
)
if d1_old in old:
    old = old.replace(d1_old, d1_new)
    print("[OK] D1 applied: page.tsx (completion gate)")
else:
    print("[WARN] D1: could not find marker in page.tsx — check file")

with open(page_path, "w") as f:
    f.write(old)

print("\nAll Phase 1 changes applied. Next steps:")
print("  1. cd ~/project/hermes_evo/AI_vedio")
print("  2. source .venv/bin/activate && python3 -m uvicorn src.api:app --reload --port 8001")
print("  3. cd web && npm run dev -- -p 3001 (in another terminal)")
print("  4. Browse http://localhost:3001")
