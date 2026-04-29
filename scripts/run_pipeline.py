#!/usr/bin/env python3
"""Run the video creation pipeline end-to-end.

Usage:
    python scripts/run_pipeline.py                    # Full run with mock data
    python scripts/run_pipeline.py --live             # Use real LLM APIs
    python scripts/run_pipeline.py --step strategy    # Run up to a specific step
"""

import asyncio
import argparse
import json
import structlog
from pathlib import Path

from langgraph.checkpoint.memory import MemorySaver

from src.graph.pipeline import compile_pipeline
from src.models.state import VideoPipelineState

logger = structlog.get_logger()

SAMPLE_INPUT = {
    "product_catalog": {
        "products": [
            {
                "name": "Wearable Breast Pump X1",
                "usps": [
                    {"priority": "P0", "text": "Hands-free, fits in bra"},
                    {"priority": "P0", "text": "Hospital-grade suction, 280mmHg"},
                    {"priority": "P1", "text": "Quiet operation, <40dB"},
                    {"priority": "P1", "text": "FDA cleared"},
                    {"priority": "P2", "text": "App-controlled"},
                ],
                "specs": {
                    "weight": "220g",
                    "battery_life": "2.5 hours",
                    "noise_level": "<40dB",
                    "capacity": "150ml per side",
                },
                "certifications": ["FDA", "CE"],
            }
        ]
    },
    "brand_guidelines": {
        "brand_name": "TestBrand",
        "tone_of_voice": {
            "archetype": "Caregiver",
            "keywords": ["warm", "empowering", "real", "professional"],
        },
        "colors": {"primary": "#FF6B9D", "secondary": "#2D3436"},
        "compliance": {
            "forbidden_claims": ["cures", "treats mastitis"],
            "required_disclaimers": ["Individual results may vary."],
        },
    },
    "target_platforms": ["tiktok", "youtube_shorts", "facebook", "shopify"],
    "target_languages": ["en"],
    "content_calendar_week": "2026-W17",
}


def print_state_summary(state: dict, step_name: str):
    """Print a human-readable summary of the current state."""
    print(f"\n{'='*60}")
    print(f"  STEP: {step_name}")
    print(f"{'='*60}")

    if state.get("weekly_calendar"):
        cal = state["weekly_calendar"]
        print(f"  Briefs: {len(cal.briefs)} generated")
        for b in cal.briefs[:2]:
            print(f"    - [{b.video_type.value}] {b.topic}")

    if state.get("scripts"):
        scripts = state["scripts"]
        print(f"  Scripts: {len(scripts)} generated")
        for s in scripts:
            print(f"    - {s.id} ({s.platform.value}): {s.total_duration}s, {len(s.segments)} segments")

    if state.get("compliance_reports"):
        reports = state["compliance_reports"]
        for r in reports:
            print(f"  Compliance [{r.script_id}]: {r.status.value} ({len(r.flags)} flags)")

    if state.get("storyboards"):
        print(f"  Storyboards: {len(state['storyboards'])} generated")

    if state.get("asset_plans"):
        print(f"  Asset Plans: {len(state['asset_plans'])} generated")

    if state.get("edit_compositions"):
        print(f"  Edit Compositions: {len(state['edit_compositions'])} generated")

    if state.get("audio_plans"):
        print(f"  Audio Plans: {len(state['audio_plans'])} generated")

    if state.get("caption_plans"):
        print(f"  Caption Plans: {len(state['caption_plans'])} generated")

    if state.get("thumbnail_sets"):
        print(f"  Thumbnail Sets: {len(state['thumbnail_sets'])} generated")

    if state.get("distribution_plans"):
        print(f"  Distribution Plans: {len(state['distribution_plans'])} generated")

    if state.get("analytics_reports"):
        print(f"  Analytics Reports: {len(state['analytics_reports'])} generated")

    if state.get("errors"):
        print(f"  ERRORS: {state['errors']}")

    if state.get("pipeline_complete"):
        print(f"\n  ✅ PIPELINE COMPLETE")


def simulate_human_approval(app, config: dict, review_nodes: list[str]):
    """Simulate human clicking 'approve' at each review checkpoint."""
    for node_name in review_nodes:
        state = app.get_state(config)
        snapshot = state.values
        human_reviews = snapshot.get("human_reviews", {})

        # Set approval
        from src.models import HumanReview, ApprovalStatus

        if node_name == "strategy_node":
            review = HumanReview(
                node="strategy_review",
                status=ApprovalStatus.APPROVED,
                reviewer_notes="Auto-approved (demo mode)",
            )
        elif node_name == "script_node":
            review = HumanReview(
                node="script_review",
                status=ApprovalStatus.APPROVED,
                reviewer_notes="Auto-approved (demo mode)",
            )
        elif node_name == "editing_node":
            review = HumanReview(
                node="edit_review",
                status=ApprovalStatus.APPROVED,
                reviewer_notes="Auto-approved (demo mode)",
            )
        elif node_name == "thumbnail_node":
            review = HumanReview(
                node="thumbnail_review",
                status=ApprovalStatus.APPROVED,
                reviewer_notes="Auto-approved (demo mode)",
            )
        else:
            continue

        # Update state with review
        reviews = dict(human_reviews)
        reviews[review.node] = review
        app.update_state(config, {"human_reviews": reviews})

        # Print what was reviewed
        print(f"\n  👤 Human Review [{review.node}]: {review.status.value}")
        print_state_summary(snapshot, node_name)


async def main():
    parser = argparse.ArgumentParser(description="Run video creation pipeline")
    parser.add_argument("--live", action="store_true", help="Use real LLM APIs (requires API keys)")
    parser.add_argument("--step", type=str, help="Run up to a specific node then stop")
    args = parser.parse_args()

    print("🎬 Short Video Agent Pipeline — MVP Demo")
    print(f"   Mode: {'LIVE (API calls)' if args.live else 'MOCK (no API keys needed)'}")

    # Build pipeline
    compiled = compile_pipeline()
    config = {"configurable": {"thread_id": "demo-run-001"}}

    # Initial state
    initial_state: VideoPipelineState = {
        "product_catalog": SAMPLE_INPUT["product_catalog"],
        "brand_guidelines": SAMPLE_INPUT["brand_guidelines"],
        "target_platforms": SAMPLE_INPUT["target_platforms"],
        "target_languages": SAMPLE_INPUT["target_languages"],
        "content_calendar_week": SAMPLE_INPUT["content_calendar_week"],
        "current_step": "init",
        "errors": [],
        "human_reviews": {},
        "pipeline_complete": False,
    }

    # Review nodes (matching interrupt_after in pipeline.py)
    review_nodes = ["strategy_node", "script_node", "editing_node", "thumbnail_node"]

    # Run with automatic approval simulation
    current_state = initial_state
    for node_name in review_nodes:
        try:
            # Run until the next interrupt
            async for event in compiled.astream(current_state, config):
                for node, output in event.items():
                    print_state_summary(output, node)

            # Simulate human approval
            simulate_human_approval(compiled, config, [node_name])

            # Get updated state for next iteration
            state_snapshot = compiled.get_state(config)
            current_state = state_snapshot.values

        except Exception as e:
            logger.error("pipeline error", node=node_name, error=str(e))
            break

    # Final: run remaining nodes (post-thumbnail)
    try:
        async for event in compiled.astream(current_state, config):
            for node, output in event.items():
                print_state_summary(output, node)
    except Exception as e:
        logger.error("pipeline error in final phase", error=str(e))

    # Export final state
    final_state = compiled.get_state(config)
    output_path = Path("output") / "pipeline_state.json"
    output_path.parent.mkdir(exist_ok=True)

    # Convert to serializable dict
    from pydantic import BaseModel

    def serialize(obj):
        if isinstance(obj, BaseModel):
            return obj.model_dump(mode="json")
        if isinstance(obj, dict):
            return {k: serialize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [serialize(v) for v in obj]
        return obj

    with open(output_path, "w") as f:
        json.dump(serialize(final_state.values), f, indent=2, default=str)

    print(f"\n📁 Full pipeline state saved to: {output_path}")
    print("✅ Done.")


if __name__ == "__main__":
    asyncio.run(main())
