#!/usr/bin/env python3
"""Orchestration script — runs full pipeline and produces renderable output.

This is the Phase 1 hardening deliverable: 
from JSON pipeline state → actual .mp4 video + thumbnails + audio.

Usage:
    python scripts/render_video.py                    # Full run with stubs
    python scripts/render_video.py --live             # Real API calls
    python scripts/render_video.py --output my_video  # Custom output name
"""

import argparse
import asyncio
from pathlib import Path

import structlog

from src.graph.pipeline import compile_pipeline
from src.models import ApprovalStatus, HumanReview
from src.tools.dalle_client import DalleClient
from src.tools.elevenlabs_client import ElevenLabsClient
from src.tools.metrics_repository import MetricsRepository
from src.tools.remotion_renderer import RemotionRenderer

logger = structlog.get_logger()

SAMPLE_INPUT = {
    "product_catalog": {
        "products": [{
            "name": "Wearable Breast Pump X1",
            "usps": [
                {"priority": "P0", "text": "Hands-free, fits in bra"},
                {"priority": "P0", "text": "Hospital-grade suction, 280mmHg"},
                {"priority": "P1", "text": "Quiet operation, <40dB"},
                {"priority": "P1", "text": "FDA cleared"},
            ],
            "specs": {"weight": "220g", "battery_life": "2.5h", "noise_level": "<40dB"},
            "certifications": ["FDA", "CE"],
        }]
    },
    "brand_guidelines": {
        "brand_name": "PumpFree",
        "tone_of_voice": {"archetype": "Caregiver", "keywords": ["warm", "empowering", "real"]},
        "colors": {"primary": "#FF6B9D", "secondary": "#2D3436"},
    },
    "target_platforms": ["tiktok"],
    "target_languages": ["en"],
    "content_calendar_week": "2026-W17",
}

REVIEW_NODES = ["strategy_review", "script_review", "edit_review", "thumbnail_review"]

# Map review node names to the audit checkpoint keys in state
AUDIT_AFTER_MAP: dict[str, str | None] = {
    "strategy_review": "strategy_complete",
    "script_review": "script_complete",
    "edit_review": "editing_complete",
    "thumbnail_review": "thumbnail_complete",
}


def _get_interrupted_after(state_values: dict) -> str | None:
    """Return which generator node just completed by checking current_step."""
    step = state_values.get("current_step", "")
    for after_node in AUDIT_AFTER_MAP.values():
        if after_node and step == after_node:
            return after_node
    return None


async def run_full_pipeline(output_name: str = "demo_output") -> dict:
    """Run the full 12-node pipeline with auto-approvals. Returns final state."""

    # ── Set up metrics repository ──
    metrics_path = Path("output") / "run_metrics.json"
    repo = MetricsRepository(path=str(metrics_path))
    repo.initialize()
    from src.telemetry import set_metrics_repo
    set_metrics_repo(repo)

    # ── Compile pipeline (uses default MemorySaver with serde registration) ──
    compiled = compile_pipeline()
    config = {"configurable": {"thread_id": f"render-{output_name}"}}

    initial_state = {
        **SAMPLE_INPUT,
        "current_step": "init",
        "errors": [],
        "human_reviews": {},
        "pipeline_complete": False,
    }

    print("🎬 Starting pipeline...\n")

    # ── Run until first interrupt (strategy_audit_node) ──
    async for event in compiled.astream(initial_state, config):
        for node in event:
            print(f"  ✓ {node}")

    # ── Loop: for each of 4 audit checkpoints, approve and resume ──
    for review_node in REVIEW_NODES:
        snapshot = compiled.get_state(config)
        after_step = _get_interrupted_after(snapshot.values)

        if after_step:
            print(f"  ⏸️  Interrupted after {after_step}")
        else:
            print(f"  ⏸️  Interrupted (no step match), current_reviews={list(snapshot.values.get('human_reviews', {}).keys())}")

        # Check if we should approve or if audit auto-decided
        audit_routing = None
        if after_step:
            # Check if the pipeline already decided routing (auto-approve/reject)
            state_audit = snapshot.values.get("audit_reports", {})
            if state_audit:
                for key, report in state_audit.items():
                    score = report.get("overall_score", 0) if isinstance(report, dict) else getattr(report, "overall_score", 0)
                    if score >= 0.90:
                        audit_routing = "auto_approve"
                    elif score < 0.60:
                        audit_routing = "auto_reject"

        if audit_routing == "auto_reject":
            print(f"  ⛔ Audit auto-rejected {review_node}. Pipeline will not proceed.")
            break

        # Auto-approve this checkpoint
        reviews = dict(snapshot.values.get("human_reviews", {}) if snapshot.values else {})
        if review_node in reviews:
            existing = reviews[review_node]
            existing_status = existing.get("status") if isinstance(existing, dict) else getattr(existing, "status", None)
            if existing_status == ApprovalStatus.APPROVED:
                print(f"  👤 {review_node} already approved")
                continue

        reviews[review_node] = HumanReview(
            node=review_node, status=ApprovalStatus.APPROVED,
            reviewer_notes="Auto-approved (CLI render mode)",
        ).model_dump()
        compiled.update_state(config, {"human_reviews": reviews})
        print(f"  👤 {review_node} approved")

        # Resume until next interrupt or end
        async for event in compiled.astream(None, config):
            for node in event:
                print(f"  ✓ {node}")

    # ── Check if pipeline completed ──
    snapshot = compiled.get_state(config)
    if snapshot.values and snapshot.values.get("pipeline_complete"):
        print("\n✅ Pipeline complete!")
    elif snapshot.next:
        print(f"\n⏸️  Pipeline paused at: {snapshot.next}")
    else:
        print("\n⚠️ Pipeline ended unexpectedly")

    state = snapshot.values if snapshot else {}
    script_count = len(state.get("scripts", [])) if state else 0
    print(f"   {script_count} scripts processed.")

    # ── Cleanup ──
    set_metrics_repo(None)
    repo.close()

    return state


async def render_outputs(pipeline_state: dict, output_name: str, use_live: bool = False):
    """Take pipeline state and produce actual files: video, audio, thumbnails."""
    renderer = RemotionRenderer()
    tts_client = ElevenLabsClient()
    dalle_client = DalleClient()

    output_dir = Path("output") / output_name
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Export full pipeline state
    print("\n📦 1/5 Exporting pipeline state...")
    json_path = renderer.export_pipeline_json(pipeline_state, f"{output_name}_state.json")
    print(f"   → {json_path}")

    # 2. Synthesize audio for first script
    print("🎙️ 2/5 Synthesizing voiceover...")
    scripts = pipeline_state.get("scripts", [])
    if scripts and use_live:
        segments = [
            {"start_time": s.start_time, "end_time": s.end_time, "text": s.voiceover}
            for s in scripts[0].segments
        ]
        audio_segments = await tts_client.synthesize_script(segments, "en")
        print(f"   → {len(audio_segments)} segments synthesized")
    else:
        print("   → Skipped (stub mode — set ELEVENLABS_API_KEY for real TTS)")

    # 3. Generate thumbnails for first script
    print("🖼️ 3/5 Generating thumbnails...")
    thumbnail_sets = pipeline_state.get("thumbnail_sets", [])
    if thumbnail_sets and use_live:
        variants = [
            {"variant_id": v.variant_id, "prompt": v.prompt}
            for v in thumbnail_sets[0].variants
        ]
        images = await dalle_client.generate_variants(variants)
        print(f"   → {len(images)} images generated")
    else:
        print("   → Skipped (stub mode — set OPENAI_API_KEY for real images)")

    # 4. Trigger Remotion render
    print("🎥 4/5 Triggering video render...")
    if renderer.is_available:
        input_json = output_dir / f"{output_name}_state.json"
        video_path = renderer.render(input_json, f"{output_name}.mp4", blocking=False)
        print(f"   → Render started (output: {video_path})")
        print("   → Check progress with: cd rendering && npx remotion studio")
    else:
        print("   → Remotion not available in this environment")
        print("   → To render locally: cd rendering && npm install && npx tsx src/render.ts")

    # 5. Print output summary
    print(f"\n{'='*50}")
    print(f"📁 Output directory: {output_dir.absolute()}")
    print(f"   Pipeline JSON: {output_name}_state.json")
    print(f"   Video: {output_name}.mp4 (rendering...)")
    print("   Audio: audio/ directory")
    print("   Thumbnails: thumbnails/ directory")
    print("\n🔑 Next steps for live rendering:")
    print("   1. Set ELEVENLABS_API_KEY in .env")
    print("   2. Set OPENAI_API_KEY in .env")
    print("   3. cd rendering && npm install")
    print("   4. python scripts/render_video.py --live")
    print(f"{'='*50}")


async def main():
    parser = argparse.ArgumentParser(description="Render a video from the pipeline")
    parser.add_argument("--live", action="store_true", help="Use real APIs (requires keys)")
    parser.add_argument("--output", type=str, default="demo_output", help="Output name")
    args = parser.parse_args()

    # Run pipeline
    state = await run_full_pipeline(output_name=args.output)

    # Render outputs
    await render_outputs(state, args.output, use_live=args.live)


if __name__ == "__main__":
    asyncio.run(main())
