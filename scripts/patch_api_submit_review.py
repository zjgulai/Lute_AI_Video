#!/usr/bin/env python3
"""
将 src/api.py 中的 submit_review 修复为 update_state + astream(None) 模式。

在 Mac 终端上运行：
    cd ~/project/hermes_evo/AI_vedio
    python scripts/patch_api_submit_review.py

然后重启后端（如果 --reload 没生效则手工重启 uvicorn）。
"""

# ── 匹配 Mac 上用的是旧代码（astream(None) 或 astream({"human_reviews": ...})） ──

# 匹配旧代码 v0: 原始的 astream(None) 版本（如果有 import structlog 的话）
OLD_V0 = '''        # Resume execution via astream — post review then wait for resume
        events = []
        try:
            async for event in _pipeline.astream(None, config):
                events.append(event)
        except Exception as e:
            import traceback

            import structlog
            log = structlog.get_logger()
            log.error("pipeline: resume failed", error=str(e), traceback=traceback.format_exc())
            raise HTTPException(status_code=500, detail=f"Pipeline resume failed: {e}")'''

# 匹配旧代码 v1: 带 import structlog 的 astream(None)
OLD_V1 = '''        # Resume execution via astream(None) — wait for next checkpoint
        events = []
        try:
            async for event in _pipeline.astream(None, config):
                events.append(event)
        except Exception as e:
            import traceback

            import structlog
            log = structlog.get_logger()
            log.error("pipeline: resume failed", error=str(e), traceback=traceback.format_exc())
            raise HTTPException(status_code=500, detail=f"Pipeline resume failed: {e}")'''

# 新代码
NEW = '''        # Step 1: Update checkpoint with the new human_review BEFORE resuming.
        # This is critical — LangGraph's routing function reads from the
        # checkpoint state to determine the next node. Without update_state,
        # the resume will replay upstream nodes and re-trigger interrupt_after.
        _pipeline.update_state(config, {"human_reviews": current_reviews})

        # Step 2: Resume via astream(None). Using None (not a dict) tells
        # LangGraph to resume from the interrupt point without re-executing
        # upstream nodes. The updated human_reviews are already in the
        # checkpoint from update_state above.
        events = []
        try:
            async for event in _pipeline.astream(None, config):
                events.append(event)
        except Exception as e:
            import traceback

            import structlog
            log = structlog.get_logger()
            log.error("pipeline: resume failed", error=str(e), traceback=traceback.format_exc())
            raise HTTPException(status_code=500, detail=f"Pipeline resume failed: {e}")'''


if __name__ == "__main__":
    import os
    import sys
    
    api_py = os.path.join(os.path.dirname(os.path.dirname(__file__)), "src", "api.py")
    
    if not os.path.exists(api_py):
        print(f"ERROR: {api_py} not found")
        sys.exit(1)
    
    with open(api_py) as f:
        content = f.read()
    
    # Try multiple patterns
    patched = False
    for old, label in [(OLD_V0, "v0 (original astream(None))"), (OLD_V1, "v1 (astream(None) with comment)")]:
        if old in content:
            content = content.replace(old, NEW)
            print(f"PATCHED src/api.py using {label}")
            patched = True
            break
    
    if not patched:
        # Check if it's already patched
        if "_pipeline.update_state(config, {\"human_reviews\": current_reviews})" in content:
            print("INFO: src/api.py already patched (update_state found). No changes needed.")
        else:
            print("ERROR: Could not match any known pattern. Showing current submit_review:")
            idx = content.find("async def submit_review")
            if idx >= 0:
                end = content.find("\n    @app.get", idx)
                print(content[idx:end if end > 0 else idx + 2000])
        sys.exit(1)
    
    with open(api_py, "w") as f:
        f.write(content)
    
    print("Patch applied. Restart uvicorn (it has --reload so should auto-detect).")
    print("  If --reload doesn't work: Ctrl+C, then re-run uvicorn.")
