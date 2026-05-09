"""A/B test tracking framework — connects gate variant selection to post-publish performance.

Records which gate candidate was chosen (standard/creative/conservative) and
the features that led to that choice. Future: correlate with metrics_poller
performance data (views, CTR, completion rate) to optimize CandidateScorer.

Usage:
    from src.quality.ab_tracker import ABTracker
    tracker = ABTracker()
    tracker.record_gate_choice(
        pipeline_label="s1-abc123",
        gate_id="gate_1",
        chosen_variant="creative",
        candidate_scores={"standard": 0.72, "creative": 0.85, "conservative": 0.68},
        script_features={"hook_duration": 2.5, "word_count": 120},
    )
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

# Default retention: keep 90 days of A/B records
DEFAULT_RETENTION_DAYS = 90


class ABTracker:
    """Lightweight A/B test tracker for gate candidate → performance correlation.

    Writes records to a JSONL file in OUTPUT_DIR. In production this should
    be backed by a database table (e.g. ab_experiments).
    """

    def __init__(self, output_dir: Path | None = None):
        self.output_dir = output_dir or OUTPUT_DIR / "ab_tracking"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        # Per-process file to avoid multi-worker write contention
        self._log_path = self.output_dir / f"gate_choices_{os.getpid()}.jsonl"

    def record_gate_choice(
        self,
        pipeline_label: str,
        gate_id: str,
        chosen_variant: str,
        candidate_scores: dict[str, float],
        script_features: dict[str, Any] | None = None,
        platform: str = "tiktok",
    ) -> None:
        """Record which gate candidate was selected and why.

        Args:
            pipeline_label: unique pipeline run identifier
            gate_id: which gate checkpoint (e.g. "gate_1", "gate_2")
            chosen_variant: which candidate was selected (standard/creative/conservative)
            candidate_scores: all candidate scores for this gate
            script_features: optional script-level features for later model training
            platform: target platform
        """
        record = {
            "ts": dt.datetime.now().isoformat(),
            "pipeline_label": pipeline_label,
            "gate_id": gate_id,
            "chosen_variant": chosen_variant,
            "candidate_scores": candidate_scores,
            "script_features": script_features or {},
            "platform": platform,
            "has_performance_data": False,
        }
        try:
            with open(self._log_path, "a") as f:
                f.write(json.dumps(record, default=str) + "\n")
            logger.info(
                "ab_tracker: recorded gate choice",
                label=pipeline_label,
                gate=gate_id,
                variant=chosen_variant,
            )
        except Exception as e:
            logger.warning("ab_tracker: failed to write record", error=str(e))

    def record_performance(
        self,
        pipeline_label: str,
        views: int | None = None,
        ctr: float | None = None,
        completion_rate: float | None = None,
        likes: int | None = None,
        shares: int | None = None,
    ) -> None:
        """Record post-publish performance metrics for a pipeline run.

        This is called by metrics_poller after the video is published and
        performance data becomes available.
        """
        record = {
            "ts": dt.datetime.now().isoformat(),
            "pipeline_label": pipeline_label,
            "type": "performance",
            "views": views,
            "ctr": ctr,
            "completion_rate": completion_rate,
            "likes": likes,
            "shares": shares,
        }
        try:
            with open(self._log_path, "a") as f:
                f.write(json.dumps(record, default=str) + "\n")
            logger.info(
                "ab_tracker: recorded performance",
                label=pipeline_label,
                views=views,
                ctr=ctr,
            )
        except Exception as e:
            logger.warning("ab_tracker: failed to write performance", error=str(e))

    def get_records(self, pipeline_label: str | None = None) -> list[dict[str, Any]]:
        """Read all tracking records, optionally filtered by pipeline label."""
        records = []
        try:
            # Read from all per-process files
            for log_file in self.output_dir.glob("gate_choices_*.jsonl"):
                with open(log_file) as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            rec = json.loads(line)
                            if pipeline_label is None or rec.get("pipeline_label") == pipeline_label:
                                records.append(rec)
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            logger.warning("ab_tracker: failed to read records", error=str(e))
        return records

    def compute_variant_performance(self) -> dict[str, Any]:
        """Aggregate performance by chosen_variant.

        Returns dict mapping variant name to average metrics.
        This is the entry point for future scorer optimization.
        """
        from collections import defaultdict

        records = self.get_records()
        # Group by pipeline_label: find gate_choice + performance pair
        by_label: dict[str, dict[str, Any]] = {}
        for rec in records:
            label = rec.get("pipeline_label", "")
            if not label:
                continue
            if label not in by_label:
                by_label[label] = {}
            if rec.get("type") == "performance":
                by_label[label]["performance"] = rec
            else:
                by_label[label]["choice"] = rec

        # Aggregate by variant
        variant_stats: dict[str, dict[str, list[float]]] = defaultdict(lambda: {"views": [], "ctr": [], "completion_rate": []})
        for label, data in by_label.items():
            choice = data.get("choice")
            perf = data.get("performance")
            if not choice or not perf:
                continue
            variant = choice.get("chosen_variant", "unknown")
            if perf.get("views") is not None:
                variant_stats[variant]["views"].append(float(perf["views"]))
            if perf.get("ctr") is not None:
                variant_stats[variant]["ctr"].append(float(perf["ctr"]))
            if perf.get("completion_rate") is not None:
                variant_stats[variant]["completion_rate"].append(float(perf["completion_rate"]))

        result: dict[str, Any] = {}
        for variant, stats in variant_stats.items():
            result[variant] = {
                "count": len(stats["views"]),
                "avg_views": round(sum(stats["views"]) / len(stats["views"]), 1) if stats["views"] else None,
                "avg_ctr": round(sum(stats["ctr"]) / len(stats["ctr"]), 4) if stats["ctr"] else None,
                "avg_completion_rate": round(sum(stats["completion_rate"]) / len(stats["completion_rate"]), 4) if stats["completion_rate"] else None,
            }
        return result
