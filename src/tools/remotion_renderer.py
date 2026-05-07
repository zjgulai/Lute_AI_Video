"""Remotion bridge — triggers video rendering from Python.

Handles:
1. Exporting pipeline state to JSON
2. Calling the Remotion render CLI
3. Tracking render progress
4. Environment validation (Node.js + Remotion)

Phase 1 fallback: outputs a render-ready JSON package with instructions.
Phase 2 (with Node.js): calls `npx tsx src/render.ts` to produce .mp4

Every public method checks is_available first and logs clear errors
when the rendering environment is not configured.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import structlog

from src.config import OUTPUT_DIR

logger = structlog.get_logger()

RENDERING_DIR = Path(__file__).parent.parent.parent / "rendering"

RENDER_SCRIPT = RENDERING_DIR / "src" / "render.ts"


class RemotionEnvironmentError(RuntimeError):
    """Raised when Node.js or Remotion is not properly installed."""


class RemotionRenderer:
    """Orchestrates video rendering via Remotion.

    Always validate with `validate_environment()` before calling render().
    Use `is_available` for quick boolean checks.
    """

    def __init__(self, output_dir: Path | None = None):
        self.output_dir = output_dir or OUTPUT_DIR / "renders"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ── Environment Validation ──

    @property
    def is_available(self) -> bool:
        """Quick check: Node.js + Remotion CLI available.

        Covers: node binary exists, npx works, remotion package is installed.
        """
        try:
            # Check Node.js
            node_result = subprocess.run(
                ["node", "--version"],
                capture_output=True, text=True, timeout=5,
            )
            if node_result.returncode != 0:
                return False

            # Check Remotion via npx
            remotion_result = subprocess.run(
                ["npx", "remotion", "--version"],
                capture_output=True, text=True, timeout=15,
                cwd=RENDERING_DIR,
            )
            return remotion_result.returncode == 0

        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            return False

    def validate_environment(self) -> dict[str, Any]:
        """Comprehensive environment check returning a structured report.

        Returns:
            dict with: available (bool), node_version, remotion_version,
            render_script_exists, node_modules_exist, issues (list[str])
        """
        issues: list[str] = []
        info: dict[str, Any] = {
            "available": False,
            "node_version": None,
            "remotion_version": None,
            "render_script_exists": False,
            "node_modules_exist": False,
            "issues": issues,
        }

        # 1. Node.js
        try:
            result = subprocess.run(
                ["node", "--version"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                info["node_version"] = result.stdout.strip()
            else:
                issues.append(f"node --version failed: {result.stderr.strip()}")
        except FileNotFoundError:
            issues.append("Node.js is not installed (node binary not found)")
        except subprocess.TimeoutExpired:
            issues.append("node --version timed out after 5s")
        except Exception as e:
            issues.append(f"node check error: {e}")

        # 2. Render script exists
        if RENDER_SCRIPT.exists():
            info["render_script_exists"] = True
        else:
            issues.append(f"Render script not found at {RENDER_SCRIPT}")

        # 3. node_modules exists
        node_modules = RENDERING_DIR / "node_modules"
        if node_modules.is_dir():
            info["node_modules_exist"] = True
        else:
            issues.append("node_modules not found — run 'npm install' in rendering/")

        # 4. Remotion CLI
        try:
            result = subprocess.run(
                ["npx", "remotion", "--version"],
                capture_output=True, text=True, timeout=15,
                cwd=RENDERING_DIR,
            )
            if result.returncode == 0:
                info["remotion_version"] = result.stdout.strip()
            else:
                issues.append(f"remotion CLI check failed: {result.stderr.strip()[:100]}")
        except subprocess.TimeoutExpired:
            issues.append("remotion --version timed out after 15s")
        except Exception as e:
            issues.append(f"remotion check error: {e}")

        info["available"] = (
            info["node_version"] is not None
            and info["remotion_version"] is not None
            and info["render_script_exists"]
            and info["node_modules_exist"]
        )
        return info

    # ── Pipeline Export ──

    def export_pipeline_json(self, pipeline_state: dict[str, Any], filename: str = "render_input.json") -> Path:
        """Export pipeline state as JSON for Remotion to consume.

        Validates environment before export — logs warning if Remotion
        is not available but still writes the JSON for manual use.
        """
        if not self.is_available:
            logger.warning(
                "remotion: environment not available — exporting JSON only",
                hint="Run 'cd rendering && npm install && npm run build' to set up Remotion",
            )

        filepath = self.output_dir / filename

        # Serialize Pydantic models
        from pydantic import BaseModel

        def serialize(obj):
            if isinstance(obj, BaseModel):
                return obj.model_dump(mode="json")
            if isinstance(obj, dict):
                return {k: serialize(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [serialize(v) for v in obj]
            if hasattr(obj, "isoformat"):
                return obj.isoformat()
            return obj

        with open(filepath, "w") as f:
            json.dump(serialize(pipeline_state), f, indent=2, default=str)

        logger.info("remotion: exported pipeline JSON", file=str(filepath))
        return filepath

    # ── Rendering ──

    def render(
        self,
        input_json: Path,
        output_filename: str = "output.mp4",
        blocking: bool = False,
    ) -> Path:
        """Trigger Remotion rendering.

        Args:
            input_json: Path to pipeline JSON.
            output_filename: Output .mp4 filename.
            blocking: If True, wait for render to complete.

        Returns:
            Path to output video (or expected path if async).

        Raises:
            RemotionEnvironmentError: if Node.js or Remotion is unavailable.
        """
        env = self.validate_environment()
        if not env["available"]:
            raise RemotionEnvironmentError(
                f"Cannot render: Remotion environment not available. "
                f"Issues: {'; '.join(env['issues'])}"
            )

        output_path = self.output_dir / output_filename

        cmd = [
            "npx", "tsx", str(RENDER_SCRIPT),
            "--input", str(input_json),
            "--output", str(output_path),
        ]

        logger.info("remotion: starting render", cmd=" ".join(cmd))

        if blocking:
            result = subprocess.run(
                cmd, cwd=RENDERING_DIR, capture_output=True, text=True, timeout=600
            )
            if result.returncode != 0:
                logger.error("remotion: render failed", stderr=result.stderr[-500:])
                raise RuntimeError(f"Remotion render failed: {result.stderr[-200:]}")
            logger.info("remotion: render complete", output=str(output_path))
        else:
            # Fire-and-forget for background rendering
            subprocess.Popen(
                cmd,
                cwd=RENDERING_DIR,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.info("remotion: render started (background)", output=str(output_path))

        return output_path
