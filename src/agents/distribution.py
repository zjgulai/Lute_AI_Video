"""Distribution Agent — multi-platform publishing plan.

Generates platform-specific post content for each target platform.
Supports: Shopify (PDP video), Amazon (A+ content), TikTok (short video),
Reddit (community post), plus YouTube Shorts, Facebook.

Each platform gets a PlatformPost with platform-optimized title,
description, post body, CTA type, and product link placeholder.

The {{product_url}} placeholder is replaced at render/publishing time.
"""
from __future__ import annotations

import structlog

from src.models import DistributionPlan, Platform, PlatformPost, Script, ThumbnailSet
from src.tools.llm_client import llm

logger = structlog.get_logger()

# ── Platform CTA type mapping ──
_PLATFORM_CTA: dict[str, str] = {
    "shopify": "add_to_cart",
    "amazon": "learn_more",
    "tiktok": "bio_link",
    "youtube_shorts": "subscribe_link",
    "facebook": "shop_now",
    "reddit": "embedded_link",
}

# ── Platform format mapping ──
_PLATFORM_FORMAT: dict[str, str] = {
    "shopify": "1:1",
    "amazon": "16:9",
    "tiktok": "9:16",
    "reddit": "9:16",
    "youtube_shorts": "9:16",
    "facebook": "1:1",
}

# ── Platform link text templates ──
_PLATFORM_LINK_TEXT: dict[str, str] = {
    "shopify": "Shop the {product_name} — link below",
    "amazon": "See the {product_name} on Amazon",
    "tiktok": "Link in bio for details",
    "reddit": "Check out {product_name} here",
}


def _hashtags_for_platform(platform: str, brief_video_type: str | None = None) -> list[str]:
    """Generate platform-appropriate hashtags."""
    base_tags = {"#wearablepump", "#pumpingmom", "#workingmom"}
    platform_tags = {
        "tiktok": base_tags | {"#momlife", "#pumping", "#fyp"},
        "shopify": base_tags | {"#handsFree", "#breastpump"},
        "amazon": base_tags | {"#pump", "#maternity"},
        "reddit": [],
    }
    return list(platform_tags.get(platform, base_tags))


class DistributionAgent:
    """Creates multi-platform publishing plans with platform-specific content.

    Uses LLM for full post body generation when available, falls back to
    template-based generation.
    """

    def __init__(self, use_mock: bool = False):
        self.use_mock = use_mock or not llm._clients

    async def run(
        self,
        scripts: list[Script],
        thumbnail_sets: list[ThumbnailSet],
        product_catalog: dict | None = None,
        target_platforms: list[str] | None = None,
    ) -> list[DistributionPlan]:
        """Generate distribution plans — one per brief, each with per-platform posts.

        Args:
            scripts: All generated scripts for all briefs.
            thumbnail_sets: Thumbnail sets.
            product_catalog: Product info for link text generation.
            target_platforms: Which platforms to post to.

        Returns:
            List of DistributionPlan, one per unique brief_id.
        """
        platforms = target_platforms or ["tiktok", "shopify", "amazon", "reddit"]
        product_name = ""
        if product_catalog:
            if isinstance(product_catalog, dict):
                product_name = product_catalog.get("product_name", "")
            elif hasattr(product_catalog, "get"):
                product_name = product_catalog.get("product_name", "")

        # Group scripts by brief_id to produce one plan per brief
        brief_groups: dict[str, list[Script]] = {}
        for s in scripts:
            bid = s.brief_id
            if bid not in brief_groups:
                brief_groups[bid] = []
            brief_groups[bid].append(s)

        plans: list[DistributionPlan] = []
        for brief_id, brief_scripts in brief_groups.items():
            posts = []
            for platform_str in platforms:
                # Find a script for this platform, or use the first one
                platform_scripts = [s for s in brief_scripts if str(s.platform) == platform_str]
                script = platform_scripts[0] if platform_scripts else brief_scripts[0]

                post = self._build_post(
                    platform_str=platform_str,
                    script=script,
                    product_name=product_name or "Product",
                    brief_id=brief_id,
                )
                posts.append(post)

            if posts:
                plans.append(DistributionPlan(
                    brief_id=brief_id,
                    script_id=brief_scripts[0].id,
                    posts=posts,
                ))

        logger.info("distribution: done", plan_count=len(plans), brief_count=len(brief_groups))
        return plans

    def _build_post(
        self,
        platform_str: str,
        script: Script,
        product_name: str,
        brief_id: str,
    ) -> PlatformPost:
        """Build a single platform-specific post."""
        first_seg = script.segments[0] if script.segments else None
        hook_text = first_seg.voiceover[:120] if first_seg and first_seg.voiceover else ""
        cta = script.cta_text or f"Check out {product_name}"

        cta_type = _PLATFORM_CTA.get(platform_str, "bio_link")
        fmt = _PLATFORM_FORMAT.get(platform_str, "9:16")
        link_text = _PLATFORM_LINK_TEXT.get(platform_str, "Learn more").format(
            product_name=product_name or "this product"
        )

        if platform_str == "tiktok":
            title = hook_text[:100] or f"{product_name} — what you need to know"
            description = cta
            post_body = ""
        elif platform_str == "shopify":
            title = f"{product_name} — Product Overview"
            description = cta
            post_body = ""
        elif platform_str == "amazon":
            title = f"{product_name} — Why Moms Love It"
            description = (
                f"{hook_text}\n\n"
                f"{cta}\n\n"
                f"Product link: {link_text}"
            )
            post_body = ""
        elif platform_str == "reddit":
            title = hook_text[:80] or f"I tried {product_name} and here's what happened"
            body_parts = [
                f"**{product_name}**",
                "",
                hook_text,
                "",
                cta,
                "",
                f"{link_text}",
            ]
            post_body = "\n".join(body_parts)
            description = cta
        else:
            title = hook_text[:100] or f"{product_name} — Quick Look"
            description = cta
            post_body = ""

        return PlatformPost(
            platform=platform_str,
            title=title,
            description=description,
            hashtags=_hashtags_for_platform(platform_str),
            video_format=fmt,
            product_link_placeholder="{{product_url}}",
            cta_type=cta_type,
            post_body=post_body,
            link_text=link_text,
        )
