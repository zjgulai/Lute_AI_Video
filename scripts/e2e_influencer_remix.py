#!/usr/bin/env python3
"""E2E Test: Influencer Remix scenario — full pipeline from start to distribution.

Handles LangGraph's interrupt_after behavior: after each astream batch that
hits an interrupt, we resume with astream(None) until pipeline_complete.

Usage:
    cd /workspace/projects/hermes_evo/AI_vedio
    python scripts/e2e_influencer_remix.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.graph.pipeline import compile_pipeline


async def main():
    print("=" * 60)
    print("E2E Test: Influencer Remix Scenario")
    print("=" * 60)
    print()

    pipeline = compile_pipeline()
    thread_id = "e2e-influencer-remix-002"
    config = {"configurable": {"thread_id": thread_id}}

    initial = {
        "product_catalog": {
            "product_name": "Wearable Breast Pump X1",
            "category": "baby",
            "usps": ["hands-free", "hospital-grade suction", "quiet <40dB"],
        },
        "brand_guidelines": {
            "brand_name": "DemoBrand",
            "tone": "warm",
            "colors": ["pink", "white"],
            "usps": ["hands-free", "quiet", "hospital-grade"],
        },
        "target_platforms": ["shopify", "amazon", "tiktok", "reddit"],
        "target_languages": ["en"],
        "content_calendar_week": "2026-W18",
        "content_scenario": "influencer_remix",
        "mock_quality": "perfect",
        "current_step": "init",
        "errors": [],
        "structured_errors": [],
        "human_reviews": {},
        "pipeline_complete": False,
    }

    print(">> Starting pipeline (influencer_remix, perfect quality)...")
    step = 0
    all_events = []

    # Phase 1: initial run
    async for event in pipeline.astream(initial, config):
        for node_name, output_obj in event.items():
            step += 1
            output = output_obj if isinstance(output_obj, dict) else output_obj.model_dump() if hasattr(output_obj, "model_dump") else {}
            all_events.append((step, node_name, output))
            node_info(node_name, output)

    # Phase 2: resume until done
    max_resumes = 20
    for resume_idx in range(max_resumes):
        snap = pipeline.get_state(config)
        if not snap.next:
            break  # pipeline complete
        async for event in pipeline.astream(None, config):
            for node_name, output_obj in event.items():
                step += 1
                output = output_obj if isinstance(output_obj, dict) else output_obj.model_dump() if hasattr(output_obj, "model_dump") else {}
                all_events.append((step, node_name, output))
                node_info(node_name, output)

    print()
    print(">> Pipeline finished. Verifying final state...")

    snapshot = pipeline.get_state(config)
    state = snapshot.values
    checks = []

    # 1. content_scenario preserved
    scenario = state.get("content_scenario", "")
    checks.append(("content_scenario=influencer_remix", scenario == "influencer_remix", scenario))

    # 2. strategy output
    cal = state.get("weekly_calendar")
    checks.append(("weekly_calendar exists", cal is not None, str(type(cal).__name__) if cal else "None"))

    # 3. scripts exist
    scripts = state.get("scripts", [])
    checks.append(("scripts exist", len(scripts) > 0, f"{len(scripts)} scripts"))

    # 4. distribution_plans exist
    plans = state.get("distribution_plans", [])
    if plans:
        plan = plans[0]
        bid = plan.brief_id if hasattr(plan, "brief_id") else plan.get("brief_id", "?")
        post_count = len(plan.posts) if hasattr(plan, "posts") else len(plan.get("posts", []))
        checks.append(("distribution_plans exist", True, f"{len(plans)} plans"))
        checks.append(("plan has brief_id", bool(bid), str(bid)))
        checks.append(("4 platform posts per plan", post_count == 4, f"{post_count} posts"))

        # Show each post
        posts = plan.posts if hasattr(plan, "posts") else plan.get("posts", [])
        for post in posts:
            p = post if hasattr(post, "platform") else post
            pid = str(p.platform if hasattr(p, "platform") else p.get("platform", "?"))
            cta = p.cta_type if hasattr(p, "cta_type") else p.get("cta_type", "")
            checks.append((f"  {pid}: {cta}", True, ""))
    else:
        checks.append(("distribution_plans exist", False, "NO PLANS"))

    # 5. pipeline_complete
    pc = state.get("pipeline_complete", False)
    checks.append(("pipeline_complete=True", pc, str(pc)))

    print()
    print("-" * 60)
    passed = sum(1 for _, ok, _ in checks if ok)
    failed = sum(1 for _, ok, _ in checks if not ok)
    for label, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}{': ' + detail if detail else ''}")

    print("-" * 60)
    print(f"  Total: {passed} passed, {failed} failed")

    if failed > 0:
        print("\n  ❌ E2E TEST FAILED")
        sys.exit(1)

    print("\n  ✅ E2E TEST PASSED")
    print()
    print("=" * 60)
    print("Distribution Plan Detail (first brief)")
    print("=" * 60)
    if plans:
        plan = plans[0]
        bid = plan.brief_id if hasattr(plan, "brief_id") else plan.get("brief_id", "?")
        sid = plan.script_id if hasattr(plan, "script_id") else plan.get("script_id", "?")
        print(f"  Brief: {bid} | Script: {sid}")
        posts = plan.posts if hasattr(plan, "posts") else plan.get("posts", [])
        for post in posts:
            p = post if hasattr(post, "platform") else post
            plt = str(p.platform if hasattr(p, "platform") else p.get("platform", "?"))
            print(f"\n  --- {plt.upper()} ---")
            print(f"    Title: {str(p.title if hasattr(p, 'title') else p.get('title', ''))[:80]}")
            print(f"    CTA: {p.cta_type if hasattr(p, 'cta_type') else p.get('cta_type', '')}")
            print(f"    Format: {p.video_format if hasattr(p, 'video_format') else p.get('video_format', '')}")
            print(f"    Placeholder: {p.product_link_placeholder if hasattr(p, 'product_link_placeholder') else p.get('product_link_placeholder', '')}")
            pb = p.post_body if hasattr(p, 'post_body') else p.get('post_body', '')
            if pb:
                print(f"    Post body: {pb[:150]}...")


def node_info(node_name: str, output: dict):
    """Print a concise summary of a node's output."""
    info_map = {
        "strategy_node": lambda o: f"{len(o.get('weekly_calendar', {}).briefs if hasattr(o.get('weekly_calendar'), 'briefs') else [])} briefs",
        "strategy_audit_node": lambda o: (lambda r: f"score={r.overall_score:.2f}" if hasattr(r, "overall_score") else "")(o.get("audit_reports", {}).get("strategy", {})),
        "script_node": lambda o: f"{len(o.get('scripts', []))} scripts",
        "script_audit_node": lambda o: (lambda r: f"score={r.overall_score:.2f}" if hasattr(r, "overall_score") else "")(o.get("audit_reports", {}).get("script", {})),
        "compliance_node": lambda o: f"{len(o.get('compliance_reports', []))} reports",
        "storyboard_node": lambda o: f"{len(o.get('storyboards', []))} storyboards",
        "asset_sourcing_node": lambda o: f"{len(o.get('asset_plans', []))} plans",
        "media_generation_node": lambda o: f"{len(o.get('generated_assets', []))} assets",
        "editing_node": lambda o: f"{len(o.get('edit_compositions', []))} comps",
        "editing_audit_node": lambda o: (lambda r: f"score={r.overall_score:.2f}" if hasattr(r, "overall_score") else "")(o.get("audit_reports", {}).get("edit", {})),
        "audio_node": lambda o: f"{len(o.get('audio_plans', []))} plans",
        "caption_node": lambda o: f"{len(o.get('caption_plans', []))} plans",
        "thumbnail_node": lambda o: f"{len(o.get('thumbnail_sets', []))} sets",
        "thumbnail_audit_node": lambda o: (lambda r: f"score={r.overall_score:.2f}" if hasattr(r, "overall_score") else "")(o.get("audit_reports", {}).get("thumbnail", {})),
        "distribution_node": lambda o: f"{len(o.get('distribution_plans', []))} plans",
        "analytics_node": lambda o: f"{len(o.get('analytics_reports', []))} reports, complete={o.get('pipeline_complete', False)}",
    }
    info = info_map.get(node_name, lambda o: str(list(o.keys())[:2]))(output)
    print(f"  [{node_name:25s}] {info}")


if __name__ == "__main__":
    asyncio.run(main())
