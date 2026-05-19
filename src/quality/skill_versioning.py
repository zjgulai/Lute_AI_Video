"""Skill versioning and performance monitoring framework.

Tracks skill execution metrics (latency, success rate, fallback rate) and
enables A/B testing between skill versions.

Usage:
    from src.quality.skill_versioning import SkillMonitor
    monitor = SkillMonitor()
    monitor.record_execution("seedance-video-generate", duration=45.2, success=True)
    report = monitor.get_report()
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any

import structlog

from src.config import OUTPUT_DIR

logger = structlog.get_logger()


class SkillMonitor:
    """Monitor skill execution performance and version tracking."""

    def __init__(self, output_dir: Path | None = None):
        self.output_dir = output_dir or OUTPUT_DIR / "skill_monitoring"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        # Per-process file to avoid multi-worker write contention
        self._log_path = self.output_dir / f"executions_{os.getpid()}.jsonl"
        # In-memory counters for current session
        self._session_counts: dict[str, dict[str, int]] = {}

    def record_execution(
        self,
        skill_name: str,
        duration_ms: float,
        success: bool,
        is_fallback: bool = False,
        error_code: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a single skill execution event."""
        record = {
            "ts": dt.datetime.now().isoformat(),
            "skill": skill_name,
            "duration_ms": round(duration_ms, 1),
            "success": success,
            "is_fallback": is_fallback,
            "error_code": error_code,
            "metadata": metadata or {},
        }

        # Update session counters
        if skill_name not in self._session_counts:
            self._session_counts[skill_name] = {"total": 0, "success": 0, "fallback": 0, "errors": 0}
        self._session_counts[skill_name]["total"] += 1
        if success:
            self._session_counts[skill_name]["success"] += 1
        if is_fallback:
            self._session_counts[skill_name]["fallback"] += 1
        if not success:
            self._session_counts[skill_name]["errors"] += 1

        try:
            with open(self._log_path, "a") as f:
                f.write(json.dumps(record, default=str) + "\n")
        except Exception as e:
            logger.warning("skill_monitor: failed to write execution log", error=str(e))

    def get_report(self, skill_name: str | None = None) -> dict[str, Any]:
        """Get performance report for all skills or a specific skill."""
        if skill_name:
            return self._get_skill_report(skill_name)

        # Aggregate across all skills in session
        all_skills = set(self._session_counts.keys())
        # Also read from disk for historical data
        try:
            if self._log_path.exists():
                with open(self._log_path) as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            rec = json.loads(line)
                            all_skills.add(rec.get("skill", ""))
                        except json.JSONDecodeError:
                            continue
        except Exception as exc:
            logger.warning(
                "skill_versioning: execution log scan failed",
                log_path=str(self._log_path),
                error=str(exc)[:200],
            )

        return {
            "skills": {s: self._get_skill_report(s) for s in all_skills if s},
            "report_generated": dt.datetime.now().isoformat(),
        }

    def _get_skill_report(self, skill_name: str) -> dict[str, Any]:
        """Get report for a single skill."""
        session = self._session_counts.get(skill_name, {})
        total = session.get("total", 0)
        success = session.get("success", 0)
        fallback = session.get("fallback", 0)
        errors = session.get("errors", 0)

        # Read from disk for latency stats (all per-process files)
        durations: list[float] = []
        try:
            for log_file in self.output_dir.glob("executions_*.jsonl"):
                with open(log_file) as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            rec = json.loads(line)
                            if rec.get("skill") == skill_name:
                                durations.append(float(rec.get("duration_ms", 0)))
                        except (json.JSONDecodeError, ValueError):
                            continue
        except Exception as exc:
            logger.warning(
                "skill_versioning: duration report scan failed",
                skill=skill_name,
                output_dir=str(self.output_dir),
                error=str(exc)[:200],
            )

        avg_dur = sum(durations) / len(durations) if durations else 0
        p95_dur = sorted(durations)[int(len(durations) * 0.95)] if len(durations) >= 20 else avg_dur

        return {
            "total_executions": total,
            "success_rate": round(success / total, 3) if total else 0,
            "fallback_rate": round(fallback / total, 3) if total else 0,
            "error_rate": round(errors / total, 3) if total else 0,
            "avg_duration_ms": round(avg_dur, 1),
            "p95_duration_ms": round(p95_dur, 1),
            "health": "healthy" if (success / total > 0.9 if total else True) else "degraded",
        }


class SkillVersionRegistry:
    """Track skill versions for A/B testing and rollback."""

    def __init__(self):
        self._versions: dict[str, dict[str, Any]] = {}

    def register_version(
        self,
        skill_name: str,
        version: str,
        is_active: bool = True,
        changelog: str = "",
    ) -> None:
        """Register a skill version."""
        if skill_name not in self._versions:
            self._versions[skill_name] = {}
        self._versions[skill_name][version] = {
            "version": version,
            "registered_at": dt.datetime.now().isoformat(),
            "is_active": is_active,
            "changelog": changelog,
        }
        logger.info(
            "skill_version: registered",
            skill=skill_name,
            version=version,
            active=is_active,
        )

    def get_active_version(self, skill_name: str) -> str | None:
        """Return the active version for a skill."""
        versions = self._versions.get(skill_name, {})
        for v, info in versions.items():
            if info.get("is_active"):
                return v
        return None

    def list_versions(self, skill_name: str) -> list[dict[str, Any]]:
        """List all versions of a skill."""
        return list(self._versions.get(skill_name, {}).values())
