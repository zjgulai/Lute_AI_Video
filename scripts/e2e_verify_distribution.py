#!/usr/bin/env python3
"""Quick E2E verification: pipepline + distribution output.

Runs pipeline with resume loop (handles all interrupt_after points).
Focuses on verifying distribution_node output with platform-specific posts.
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.graph.pipeline import compile_pipeline


async def main():
    pipeline = compile_pipeline()
    thread_id = "e2e-quick-001"
    config = {"configurable": {"thread_id": thread_id}}

    initial = {
        "product_catalog": {
            "product_name": "Wearable Breast Pump X1",
            "usps": ["hands-free", "hospital-grade suction", "quiet <40dB"],
        },
        "brand_guidelines": {"tone": "warm", "colors": ["pink", "white"]},
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

    # Initial run
    async for _ in pipeline.astream(initial, config):
        pass

    # Resume loop
    for _ in range(30):
        snap = pipeline.get_state(config)
        if not snap.next:
            break
        async for _ in pipeline.astream(None, config):
            pass

    # Verify
    snap = pipeline.get_state(config)
    state = snap.values

    scenario = state.get("content_scenario", "")
    scripts = state.get("scripts", [])
    plans = state.get("distribution_plans", [])
    complete = state.get("pipeline_complete", False)

    print(f"content_scenario: {scenario}")
    print(f"scripts: {len(scripts)}")
    print(f"distribution_plans: {len(plans)}")
    print(f"pipeline_complete: {complete}")

    if plans:
        plan = plans[0]
        bid = plan.brief_id if hasattr(plan, 'brief_id') else plan.get('brief_id', '?')
        sid = plan.script_id if hasattr(plan, 'script_id') else plan.get('script_id', '?')
        print(f"\n--- First Plan: Brief={bid}, Script={sid} ---")
        posts = plan.posts if hasattr(plan, 'posts') else plan.get('posts', [])
        for p in posts:
            post = p if hasattr(p, 'platform') else p
            print(f"  Platform: {post.platform}")
            print(f"    CTA type: {post.cta_type}")
            print(f"    Format: {post.video_format}")
            print(f"    Placeholder: {post.product_link_placeholder}")
            print(f"    Link text: {post.link_text[:80] if hasattr(post, 'link_text') else 'N/A'}")
            body = post.post_body if hasattr(post, 'post_body') else ''
            if body:
                print(f"    Post body: {body[:120]}...")
    else:
        print("\n⚠️  NO distribution_plans — check pipeline execution")
        print(f"  Next: {snap.next}")
        print(f"  Step: {state.get('current_step', '?')}")


if __name__ == "__main__":
    asyncio.run(main())
