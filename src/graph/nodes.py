"""12 pipeline node functions.

Each node: receives state → does work → returns updated state dict.
All 12 + 4 audit nodes are decorated with @timed_node for metrics collection.
"""

from __future__ import annotations

from typing import Any

import structlog

from src.models.state import VideoPipelineState
from src.telemetry import timed_node
from src.tools.webhook_manager import get_webhook_manager

logger = structlog.get_logger()


# ── L4.4 / L5.x helpers ──


def _inject_rejection_feedback(
    state: VideoPipelineState,
    review_key: str,
    feedback_key: str,
) -> dict[str, str]:
    """L4.4: On re-entry, extract reviewer_notes from human_reviews.

    Returns the updated (or unchanged) rejection_feedback dict.
    """
    rejection_feedback = dict(state.get("rejection_feedback", {}))
    if feedback_key not in rejection_feedback:
        review = state.get("human_reviews", {}).get(review_key)
        if review:
            notes = (
                review.get("reviewer_notes", "")
                if isinstance(review, dict)
                else getattr(review, "reviewer_notes", "")
            )
            if notes:
                rejection_feedback[feedback_key] = notes
    return rejection_feedback


def _make_self_verification(
    node_name: str,
    checks: dict[str, bool],
    summary: str,
) -> dict[str, Any]:
    """L5.x: Build a self-verification record for a node execution."""
    return {
        "node_name": node_name,
        "output_summary": summary,
        "quality_thresholds_met": all(checks.values()),
        "verification_details": checks,
    }


# ═══════════════════════════════════════════
# Node 1: Strategy Agent
# ═══════════════════════════════════════════


@timed_node
async def strategy_node(state: VideoPipelineState) -> dict[str, Any]:
    """Generate weekly content briefs from product catalog + brand guidelines."""
    from src.agents.strategy import StrategyAgent

    mock_quality = state.get("mock_quality")
    content_scenario = state.get("content_scenario", "general")
    agent = StrategyAgent(quality_level=mock_quality, content_scenario=content_scenario)
    calendar = await agent.run(
        product_catalog=state.get("product_catalog", {}),
        brand_guidelines=state.get("brand_guidelines", {}),
        target_platforms=state.get("target_platforms", ["shopify", "amazon", "tiktok", "reddit"]),
        target_languages=state.get("target_languages", ["en"]),
        week=state.get("content_calendar_week", "2026-W17"),
    )
    logger.info("strategy_node: done", brief_count=len(calendar.briefs))
    return {"weekly_calendar": calendar, "current_step": "strategy_complete"}


# ═══════════════════════════════════════════
# Node 2: Script Writer Agent
# ═══════════════════════════════════════════


@timed_node
async def script_node(state: VideoPipelineState) -> dict[str, Any]:
    """Convert each brief into platform-adapted scripts.

    Reads strategy audit quality signals from state and passes them
    to the ScriptWriterAgent so scripts compensate for strategic weaknesses.
    """
    from src.agents.script_writer import ScriptWriterAgent

    agent = ScriptWriterAgent()
    calendar = state.get("weekly_calendar")
    if not calendar:
        return {"errors": ["No weekly_calendar in state — cannot write scripts"]}

    # Extract strategy audit report for quality feedback propagation
    strategy_audit = state.get("audit_reports", {}).get("strategy", None)

    scripts = await agent.run(
        briefs=calendar.briefs,
        brand_guidelines=state.get("brand_guidelines", {}),
        strategy_audit=strategy_audit,
        target_languages=state.get("target_languages", ["en"]),
    )
    logger.info("script_node: done", script_count=len(scripts))
    return {"scripts": scripts, "current_step": "script_complete"}


# ═══════════════════════════════════════════
# Node 3: Compliance Agent
# ═══════════════════════════════════════════


@timed_node
async def compliance_node(state: VideoPipelineState) -> dict[str, Any]:
    """Check all scripts for platform compliance and content policy violations.

    Uses script_audit_node's Compliance Pre-check criterion to short-circuit
    full rule engine scan when all scripts are already pre-cleared.
    """
    from src.agents.compliance import ComplianceAgent

    agent = ComplianceAgent()
    scripts = state.get("scripts", [])

    # Read script audit report for compliance pre-check short-circuit
    script_audit_report = state.get("audit_reports", {}).get("script", None)

    reports = await agent.run(scripts=scripts, script_audit_report=script_audit_report)
    logger.info("compliance_node: done", report_count=len(reports))
    return {"compliance_reports": reports, "current_step": "compliance_complete"}


# ═══════════════════════════════════════════
# Node 4: Storyboard Agent
# ═══════════════════════════════════════════


@timed_node
async def storyboard_node(state: VideoPipelineState) -> dict[str, Any]:
    """Convert scripts into visual shot lists."""
    from src.agents.storyboard import StoryboardAgent

    agent = StoryboardAgent()
    scripts = state.get("scripts", [])
    storyboards = await agent.run(scripts=scripts)
    logger.info("storyboard_node: done", sb_count=len(storyboards))
    return {"storyboards": storyboards, "current_step": "storyboard_complete"}


# ═══════════════════════════════════════════
# Node 5: Asset Sourcing Agent
# ═══════════════════════════════════════════


@timed_node
async def asset_sourcing_node(state: VideoPipelineState) -> dict[str, Any]:
    """Match storyboard shot requirements to asset library.

    If asset_plans already exist (e.g. injected via update_state for testing),
    skip regeneration and return existing plans.
    """
    from src.agents.asset_sourcing import AssetSourcingAgent

    # Allow tests to inject pre-computed asset plans to control gap behavior
    existing = state.get("asset_plans")
    if existing and len(existing) > 0:
        logger.info("asset_sourcing_node: using pre-existing plans", plan_count=len(existing))
        return {"asset_plans": existing, "current_step": "asset_sourcing_complete"}

    agent = AssetSourcingAgent()
    storyboards = state.get("storyboards", [])
    asset_plans = await agent.run(storyboards=storyboards)
    logger.info("asset_sourcing_node: done", plan_count=len(asset_plans))
    return {"asset_plans": asset_plans, "current_step": "asset_sourcing_complete"}


# ═══════════════════════════════════════════
# Node 6: AI Media Generation (stub)
# ═══════════════════════════════════════════


@timed_node
async def media_generation_node(state: VideoPipelineState) -> dict[str, Any]:
    """Generate AI assets for gaps in the asset plan (MVP: stub)."""
    from src.agents.media_generation import MediaGenerationAgent

    agent = MediaGenerationAgent()
    asset_plans = state.get("asset_plans", [])
    generated = await agent.run(asset_plans=asset_plans)
    logger.info("media_generation_node: done", gen_count=len(generated))
    return {"generated_assets": generated, "current_step": "media_generation_complete"}


# ═══════════════════════════════════════════
# Node 7: Video Editing Agent
# ═══════════════════════════════════════════


@timed_node
async def editing_node(state: VideoPipelineState) -> dict[str, Any]:
    """Assemble assets + storyboard → edit composition timeline."""
    from src.agents.editor import EditingAgent

    agent = EditingAgent()
    storyboards = state.get("storyboards", [])
    asset_plans = state.get("asset_plans", [])
    compositions = await agent.run(storyboards=storyboards, asset_plans=asset_plans)
    logger.info("editing_node: done", comp_count=len(compositions))
    return {"edit_compositions": compositions, "current_step": "editing_complete"}


# ═══════════════════════════════════════════
# Node 8: Audio Design Agent
# ═══════════════════════════════════════════


@timed_node
async def audio_node(state: VideoPipelineState) -> dict[str, Any]:
    """Generate TTS voiceover + BGM plan."""
    from src.agents.audio_designer import AudioDesignAgent

    agent = AudioDesignAgent()
    scripts = state.get("scripts", [])
    audio_plans = await agent.run(scripts=scripts)
    logger.info("audio_node: done", plan_count=len(audio_plans))
    return {"audio_plans": audio_plans, "current_step": "audio_complete"}


# ═══════════════════════════════════════════
# Node 9: Caption Agent
# ═══════════════════════════════════════════


@timed_node
async def caption_node(state: VideoPipelineState) -> dict[str, Any]:
    """Generate timed caption tracks + text overlay styling."""
    from src.agents.caption import CaptionAgent

    agent = CaptionAgent()
    scripts = state.get("scripts", [])
    caption_plans = await agent.run(scripts=scripts)
    logger.info("caption_node: done", plan_count=len(caption_plans))
    return {"caption_plans": caption_plans, "current_step": "caption_complete"}


# ═══════════════════════════════════════════
# Node 10: Thumbnail Agent
# ═══════════════════════════════════════════


@timed_node
async def thumbnail_node(state: VideoPipelineState) -> dict[str, Any]:
    """Generate 4 thumbnail variants per video.

    Receives caption_plans from state and propagates visual emphasis
    signals (highlighted text, CTA entries, key phrases) into DALL-E prompts —
    so thumbnails visually align with what the captions emphasized.
    """
    from src.agents.thumbnail import ThumbnailAgent

    mock_quality = state.get("mock_quality")
    if mock_quality:
        # Mock mode: bypass DALL-E, use deterministic quality-test data
        from src.data.mock_quality import degrade_thumbnails, QualityLevel
        try:
            level = QualityLevel(mock_quality)
        except ValueError:
            level = QualityLevel.PERFECT
        thumbnail_sets = degrade_thumbnails(level)
    else:
        agent = ThumbnailAgent()
        scripts = state.get("scripts", [])
        caption_plans = state.get("caption_plans", None)
        thumbnail_sets = await agent.run(scripts=scripts, caption_plans=caption_plans)

    # Track retry count so route_after_thumbnail can break infinite loops
    retry_counts = dict(state.get("retry_counts", {}))
    retry_counts["thumbnail"] = retry_counts.get("thumbnail", 0) + 1

    logger.info("thumbnail_node: done", set_count=len(thumbnail_sets), retry_count=retry_counts.get("thumbnail"))
    return {
        "thumbnail_sets": thumbnail_sets,
        "current_step": "thumbnail_complete",
        "retry_counts": retry_counts,
    }


# ═══════════════════════════════════════════
# Node 11: Distribution Agent
# ═══════════════════════════════════════════


@timed_node
async def distribution_node(state: VideoPipelineState) -> dict[str, Any]:
    """Create multi-platform publishing plan with platform-specific content."""
    from src.agents.distribution import DistributionAgent

    agent = DistributionAgent()
    scripts = state.get("scripts", [])
    thumbnail_sets = state.get("thumbnail_sets", [])
    dist_plans = await agent.run(
        scripts=scripts,
        thumbnail_sets=thumbnail_sets,
        product_catalog=state.get("product_catalog"),
        target_platforms=state.get("target_platforms"),
    )
    logger.info("distribution_node: done", plan_count=len(dist_plans))
    return {"distribution_plans": dist_plans, "current_step": "distribution_complete"}


# ═══════════════════════════════════════════
# Node 12: Analytics Agent
# ═══════════════════════════════════════════


@timed_node
async def analytics_node(state: VideoPipelineState) -> dict[str, Any]:
    """Generate analytics report (MVP: template with mock data)."""
    from src.agents.analytics import AnalyticsAgent

    agent = AnalyticsAgent()
    scripts = state.get("scripts", [])
    week = state.get("content_calendar_week", "2026-W17")
    reports = await agent.run(scripts=scripts, week=week)
    logger.info("analytics_node: done")
    # GAP-17: Dispatch webhook
    wh = get_webhook_manager()
    metrics = state.get("pipeline_metrics", {})
    wh.dispatch_sync("pipeline.completed", {
        "thread_id": state.get("content_calendar_week", ""),
        "total_duration_ms": metrics.get("total_duration_ms", 0),
        "node_count": metrics.get("node_count", 0),
        "error_count": metrics.get("error_count", 0),
    })

    # GAP-19: Persist metrics for cross-run analysis
    _try_save_metrics(state)
    return {
        "analytics_reports": reports,
        "current_step": "analytics_complete",
        "pipeline_complete": True,
    }


def _try_save_metrics(state: VideoPipelineState) -> None:
    """Attempt to persist pipeline metrics via configured repository.

    Non-blocking: logs and swallows all errors.
    """
    try:
        from src.telemetry import save_run_metrics

        metrics = state.get("pipeline_metrics", {})
        if metrics:
            save_run_metrics(metrics)
    except Exception:
        pass


# ═══════════════════════════════════════════
# Audit Nodes (run after generator, before human review)
# ═══════════════════════════════════════════


@timed_node
async def strategy_audit_node(state: VideoPipelineState) -> dict[str, Any]:
    """Self-audit the weekly content calendar before human review #1.

    Increments retry_counts['strategy'] on re-entry to prevent infinite loops.
    L4.4: Injects rejection feedback on re-entry.
    L5.x: Collects self-verification from strategy_node output.
    """
    from src.agents.auditor import AuditorAgent

    retry_counts = dict(state.get("retry_counts", {}))
    self_verifications = dict(state.get("self_verifications", {}))

    is_reentry = "strategy" in state.get("audit_reports", {})
    if is_reentry:
        # Unconditional increment — any re-entry counts as a retry,
        # regardless of human review status, to guarantee route_after_strategy's
        # retry_guard can break infinite auto-review loops (score in middle range).
        retry_counts["strategy"] = retry_counts.get("strategy", 0) + 1

    rejection_feedback = _inject_rejection_feedback(state, "strategy_review", "strategy")

    agent = AuditorAgent()
    calendar = state.get("weekly_calendar")
    if not calendar:
        return {"errors": ["No weekly_calendar to audit"]}

    # L5.x: Build self-verification for strategy_node
    brief_count = len(calendar.briefs)
    platforms = set()
    for b in calendar.briefs:
        for p in b.target_platforms:
            platforms.add(p.value if hasattr(p, "value") else str(p))
    self_verifications["strategy_node"] = _make_self_verification(
        "strategy_node",
        {"has_briefs": brief_count > 0, "has_platforms": len(platforms) > 0, "week_set": bool(calendar.week)},
        f"{brief_count} briefs covering {len(platforms)} platforms, week {calendar.week}",
    )

    report = await agent.run_strategy_audit(
        calendar=calendar,
        target_platforms=state.get("target_platforms", []),
        brand_guidelines=state.get("brand_guidelines"),
    )
    audit_reports = state.get("audit_reports", {})
    audit_reports["strategy"] = report
    logger.info(
        "strategy_audit_node: done",
        score=report.overall_score,
        status=report.overall_status.value,
        retry_count=retry_counts.get("strategy", 0),
    )
    # GAP-17: Dispatch webhook
    wh = get_webhook_manager()
    wh.dispatch_sync("audit.completed", {
        "checkpoint": "strategy",
        "score": report.overall_score,
        "status": report.overall_status.value,
        "summary": report.summary,
        "thread_id": state.get("content_calendar_week", ""),
    })
    return {
        "audit_reports": audit_reports,
        "current_step": "strategy_audit_complete",
        "retry_counts": retry_counts,
        "rejection_feedback": rejection_feedback,
        "self_verifications": self_verifications,
    }


@timed_node
async def script_audit_node(state: VideoPipelineState) -> dict[str, Any]:
    """Self-audit all scripts before human review #2.

    Increments retry_counts['script'] on re-entry to prevent infinite loops.
    L4.4: Injects rejection feedback on re-entry.
    L5.x: Collects self-verification from script_node output.
    """
    from src.agents.auditor import AuditorAgent

    retry_counts = dict(state.get("retry_counts", {}))
    self_verifications = dict(state.get("self_verifications", {}))

    is_reentry = "script" in state.get("audit_reports", {})
    if is_reentry:
        # Unconditional increment — any re-entry counts as a retry,
        # regardless of human review status, to guarantee route_after_script's
        # retry_guard can break infinite auto-review loops.
        retry_counts["script"] = retry_counts.get("script", 0) + 1

    rejection_feedback = _inject_rejection_feedback(state, "script_review", "script")

    agent = AuditorAgent()
    scripts = state.get("scripts", [])
    if not scripts:
        return {"errors": ["No scripts to audit"]}

    # L5.x: Build self-verification for script_node
    total_duration = sum(s.total_duration for s in scripts) if scripts else 0
    platforms = set(s.platform.value if hasattr(s.platform, "value") else str(s.platform) for s in scripts)
    has_cta = any(s.cta_text.strip() for s in scripts)
    self_verifications["script_node"] = _make_self_verification(
        "script_node",
        {
            "has_scripts": len(scripts) > 0,
            "all_have_cta": has_cta,
            "platforms_covered": len(platforms) > 0,
        },
        f"{len(scripts)} scripts, {len(platforms)} platforms, {total_duration:.0f}s total duration",
    )

    reports = await agent.run_script_audit(
        scripts=scripts,
        brand_guidelines=state.get("brand_guidelines"),
    )
    # Store per-script audit reports — use the first one as primary for checkpoint
    # (human reviews all scripts together at this checkpoint)
    audit_reports = state.get("audit_reports", {})
    audit_reports["script"] = reports[0] if reports else None
    logger.info(
        "script_audit_node: done",
        report_count=len(reports),
        avg_score=sum(r.overall_score for r in reports) / len(reports) if reports else 0,
        retry_count=retry_counts.get("script", 0),
    )
    # GAP-17: Dispatch webhook
    wh = get_webhook_manager()
    wh.dispatch_sync("audit.completed", {
        "checkpoint": "script",
        "score": sum(r.overall_score for r in reports) / len(reports) if reports else 0,
        "status": reports[0].overall_status.value if reports else "unknown",
        "summary": reports[0].summary if reports else "",
        "thread_id": state.get("content_calendar_week", ""),
    })
    return {
        "audit_reports": audit_reports,
        "current_step": "script_audit_complete",
        "retry_counts": retry_counts,
        "rejection_feedback": rejection_feedback,
        "self_verifications": self_verifications,
    }


@timed_node
async def editing_audit_node(state: VideoPipelineState) -> dict[str, Any]:
    """Self-audit edit compositions before human review #3.

    Increments retry_counts['edit'] on re-entry to prevent infinite loops.
    L4.4: Injects rejection feedback on re-entry.
    L5.x: Collects self-verification from editing_node output.
    """
    from src.agents.auditor import AuditorAgent

    retry_counts = dict(state.get("retry_counts", {}))
    self_verifications = dict(state.get("self_verifications", {}))

    is_reentry = "edit" in state.get("audit_reports", {})
    if is_reentry:
        # Unconditional increment — any re-entry counts as a retry,
        # regardless of human review status, to guarantee route_after_editing's
        # retry_guard can break infinite auto-review loops.
        retry_counts["edit"] = retry_counts.get("edit", 0) + 1

    rejection_feedback = _inject_rejection_feedback(state, "edit_review", "edit")

    agent = AuditorAgent()
    compositions = state.get("edit_compositions", [])
    if not compositions:
        return {"errors": ["No edit compositions to audit"]}

    # L5.x: Build self-verification for editing_node
    total_events = sum(len(c.timeline) for c in compositions) if compositions else 0
    has_transitions = any(e.transition != "cut" for c in compositions for e in c.timeline) if compositions else False
    self_verifications["editing_node"] = _make_self_verification(
        "editing_node",
        {
            "has_compositions": len(compositions) > 0,
            "has_timeline_events": total_events > 0,
            "has_varied_transitions": has_transitions,
        },
        f"{len(compositions)} compositions, {total_events} timeline events",
    )

    reports = await agent.run_edit_audit(compositions)
    audit_reports = state.get("audit_reports", {})
    audit_reports["edit"] = reports[0] if reports else None
    logger.info(
        "editing_audit_node: done",
        report_count=len(reports),
        retry_count=retry_counts.get("edit", 0),
    )
    # GAP-17: Dispatch webhook
    wh = get_webhook_manager()
    wh.dispatch_sync("audit.completed", {
        "checkpoint": "edit",
        "score": reports[0].overall_score if reports else 0,
        "status": reports[0].overall_status.value if reports else "unknown",
        "summary": reports[0].summary if reports else "",
        "thread_id": state.get("content_calendar_week", ""),
    })
    return {
        "audit_reports": audit_reports,
        "current_step": "edit_audit_complete",
        "retry_counts": retry_counts,
        "rejection_feedback": rejection_feedback,
        "self_verifications": self_verifications,
    }


@timed_node
async def thumbnail_audit_node(state: VideoPipelineState) -> dict[str, Any]:
    """Self-audit thumbnail sets before human review #4.

    Increments retry_counts['thumbnail'] on re-entry to prevent infinite loops.
    L4.4: Injects rejection feedback on re-entry.
    L5.x: Collects self-verification from thumbnail_node output.
    """
    from src.agents.auditor import AuditorAgent

    retry_counts = dict(state.get("retry_counts", {}))
    self_verifications = dict(state.get("self_verifications", {}))

    is_reentry = "thumbnail" in state.get("audit_reports", {})
    if is_reentry:
        # Unconditional increment — any re-entry counts as a retry,
        # regardless of human review status, to guarantee route_after_thumbnail's
        # retry_guard can break infinite auto-review loops (score in middle range).
        retry_counts["thumbnail"] = retry_counts.get("thumbnail", 0) + 1

    rejection_feedback = _inject_rejection_feedback(state, "thumbnail_review", "thumbnail")

    agent = AuditorAgent()
    thumbnail_sets = state.get("thumbnail_sets", [])
    if not thumbnail_sets:
        return {"errors": ["No thumbnail sets to audit"]}

    # L5.x: Build self-verification for thumbnail_node
    total_variants = sum(len(ts.variants) for ts in thumbnail_sets) if thumbnail_sets else 0
    has_selection = any(ts.selected_variant_id for ts in thumbnail_sets) if thumbnail_sets else False
    self_verifications["thumbnail_node"] = _make_self_verification(
        "thumbnail_node",
        {
            "has_thumbnail_sets": len(thumbnail_sets) > 0,
            "has_variants": total_variants > 0,
            "has_selection": has_selection,
        },
        f"{len(thumbnail_sets)} sets, {total_variants} variants",
    )

    reports = await agent.run_thumbnail_audit(
        thumbnail_sets=thumbnail_sets,
        brand_guidelines=state.get("brand_guidelines"),
    )
    audit_reports = state.get("audit_reports", {})
    audit_reports["thumbnail"] = reports[0] if reports else None
    logger.info(
        "thumbnail_audit_node: done",
        report_count=len(reports),
        retry_count=retry_counts.get("thumbnail", 0),
    )
    # GAP-17: Dispatch webhook
    wh = get_webhook_manager()
    wh.dispatch_sync("audit.completed", {
        "checkpoint": "thumbnail",
        "score": reports[0].overall_score if reports else 0,
        "status": reports[0].overall_status.value if reports else "unknown",
        "summary": reports[0].summary if reports else "",
        "thread_id": state.get("content_calendar_week", ""),
    })
    return {
        "audit_reports": audit_reports,
        "current_step": "thumbnail_audit_complete",
        "retry_counts": retry_counts,
        "rejection_feedback": rejection_feedback,
        "self_verifications": self_verifications,
    }
