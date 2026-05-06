#!/usr/bin/env python3
"""Check frontend/backend STEP_ORDER consistency.

CI lint: fails if frontend fallback STEP_ORDER diverges from backend.

Usage:
    python scripts/check_step_order_consistency.py
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def _extract_ts_string_array(file_path: Path, var_name: str) -> list[str] | None:
    """Extract a const string[] from TypeScript source via regex."""
    text = file_path.read_text()
    # Match: const NAME = [\n  "a",\n  "b",\n];
    pattern = rf"const\s+{re.escape(var_name)}\s*=\s*\[(.*?)\];"
    m = re.search(pattern, text, re.DOTALL)
    if not m:
        return None
    items = re.findall(r'"([^"]+)"', m.group(1))
    return items


def _extract_py_list(file_path: Path, var_name: str) -> list[str] | None:
    """Extract a Python list[str] from source via AST."""
    text = file_path.read_text()
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == var_name:
                    if isinstance(node.value, ast.List):
                        return [
                            elt.value
                            for elt in node.value.elts
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                        ]
    return None


def main() -> int:
    backend_steps = _extract_py_list(
        PROJECT_ROOT / "src" / "pipeline" / "step_runner.py", "STEP_ORDER"
    )
    if backend_steps is None:
        print("ERROR: Could not extract STEP_ORDER from step_runner.py")
        return 1

    frontend_files = [
        ("web/src/components/VideoWorkflow.tsx", "_FALLBACK_STEP_ORDER"),
        ("web/src/components/StepByStepView.tsx", "_FALLBACK_STEP_ORDER"),
    ]

    all_ok = True
    for rel_path, var_name in frontend_files:
        path = PROJECT_ROOT / rel_path
        frontend_steps = _extract_ts_string_array(path, var_name)
        if frontend_steps is None:
            print(f"ERROR: Could not extract {var_name} from {rel_path}")
            all_ok = False
            continue

        if frontend_steps != backend_steps:
            print(f"MISMATCH: {rel_path} {var_name}")
            print(f"  backend: {backend_steps}")
            print(f"  frontend: {frontend_steps}")
            # Diff
            only_backend = [s for s in backend_steps if s not in frontend_steps]
            only_frontend = [s for s in frontend_steps if s not in backend_steps]
            if only_backend:
                print(f"  only in backend: {only_backend}")
            if only_frontend:
                print(f"  only in frontend: {only_frontend}")
            all_ok = False
        else:
            print(f"OK: {rel_path} {var_name} matches backend ({len(backend_steps)} steps)")

    if all_ok:
        print("All STEP_ORDER sources are consistent.")
        return 0
    else:
        print("\nFix: update frontend _FALLBACK_STEP_ORDER to match backend STEP_ORDER.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
