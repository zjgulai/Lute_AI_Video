"""Platform Safe Zone checker — ensures captions/text don't get hidden by platform UI.

TikTok / YouTube Shorts / Instagram Reels overlay UI elements at:
- Top ~15%: username, music info, following button
- Bottom ~15%: like, comment, share, sound controls, captions
- Left/right edges: minimal UI

Safe zone for text overlays: y position between 15% and 75% of frame height.

Usage:
    from src.quality.safe_zone import SafeZoneChecker
    ok = SafeZoneChecker().check_caption_position(y_percent=20, text_lines=2)
"""

from __future__ import annotations

from typing import Any

# Platform UI overlay zones (percentage of frame height from top)
PLATFORM_SAFE_ZONES = {
    "tiktok": {"top_margin": 15, "bottom_margin": 20, "side_margin": 5},
    "youtube_shorts": {"top_margin": 12, "bottom_margin": 15, "side_margin": 5},
    "instagram_reels": {"top_margin": 14, "bottom_margin": 18, "side_margin": 5},
}

# Max text lines that fit in safe zone (rough estimate)
MAX_LINES_IN_SAFE_ZONE = 3


class SafeZoneChecker:
    """Check if text/caption positions are within platform safe zones."""

    def check_caption_position(
        self,
        y_percent: float,
        text_lines: int = 1,
        platform: str = "tiktok",
    ) -> dict[str, Any]:
        """Check if a caption at y_percent vertical position is safe.

        Args:
            y_percent: vertical position as % from top (0 = top, 100 = bottom)
            text_lines: number of lines of text
            platform: target platform key

        Returns:
            {"safe": bool, "issues": list[str], "recommendation": str}
        """
        zones = PLATFORM_SAFE_ZONES.get(platform, PLATFORM_SAFE_ZONES["tiktok"])
        top_limit = zones["top_margin"]
        bottom_limit = 100 - zones["bottom_margin"]

        issues: list[str] = []

        if y_percent < top_limit:
            issues.append(f"y={y_percent:.0f}% is in top UI zone (≥{top_limit}% recommended)")

        # Estimate text height: ~5% per line
        text_height = text_lines * 5.0
        if y_percent + text_height > bottom_limit:
            issues.append(
                f"text extends to y={y_percent + text_height:.0f}%, "
                f"entering bottom UI zone (≤{bottom_limit}% recommended)"
            )

        if text_lines > MAX_LINES_IN_SAFE_ZONE:
            issues.append(f"{text_lines} lines may not fit in safe zone (max {MAX_LINES_IN_SAFE_ZONE})")

        safe = len(issues) == 0
        return {
            "safe": safe,
            "platform": platform,
            "y_percent": y_percent,
            "text_lines": text_lines,
            "safe_zone": f"{top_limit}%–{bottom_limit}%",
            "issues": issues,
            "recommendation": "Move text to center of frame (30-60% y)" if not safe else "",
        }

    def check_drawtext_filter(
        self,
        y_expression: str,
        platform: str = "tiktok",
    ) -> dict[str, Any]:
        """Parse an ffmpeg drawtext y= expression and check safety.

        Supports common expressions:
        - "(h-text_h)/2" → center
        - "h-text_h-80" → near bottom
        - "20" → absolute pixels
        """
        # Rough heuristic: if expression contains "h-text_h" it's near bottom
        expr = y_expression.lower().replace(" ", "")

        if "h-text_h" in expr or "h-th" in expr:
            # Near bottom — check if it's too close
            if "-80" in expr or "-100" in expr or "-120" in expr:
                return {
                    "safe": False,
                    "platform": platform,
                    "y_expression": y_expression,
                    "issues": ["drawtext y position is near bottom — may be covered by platform UI"],
                    "recommendation": "Use y=(h-text_h)/2 or y=(h*0.4) for safe center placement",
                }

        if "(h-text_h)/2" in expr or "(h-th)/2" in expr:
            return {
                "safe": True,
                "platform": platform,
                "y_expression": y_expression,
                "issues": [],
                "recommendation": "",
            }

        # Default: assume center is safe, anything else needs review
        return {
            "safe": True,
            "platform": platform,
            "y_expression": y_expression,
            "issues": [],
            "recommendation": "",
            "note": "y expression could not be fully parsed — manual review recommended",
        }
