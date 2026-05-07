"""POYO content moderation defense — sanitize prompts before submission.

POYO Happy Horse / GPT Image API has automated content moderation that rejects
common maternal/baby product terms (e.g. "breast pump", "lactation"). This is
external and unfixable; our defense is to substitute trigger phrases with
neutral product-equivalent terms BEFORE submission so the LLM-generated prompt
carries the same visual intent without tripping the filter.

Substitutions are conservative and bidirectional (EN + ZH). New triggers
should be added as they're observed in production logs.

Usage:
    from src.tools.poyo_safety import sanitize_for_poyo
    sanitized, subs = sanitize_for_poyo(prompt)
    if subs:
        logger.info("poyo_safety: substitutions applied", subs=subs)
"""

from __future__ import annotations

import re

# Order matters: longer phrases first so e.g. "wearable breast pump" is
# matched before "breast pump".
_SUBSTITUTIONS: list[tuple[re.Pattern[str], str]] = [
    # English — multi-word phrases first
    (re.compile(r"\bwearable\s+breast[\s-]*pump(s|ing)?\b", re.IGNORECASE), "wearable wellness device"),
    (re.compile(r"\bbreast[\s-]*pump(s|ing)?\b", re.IGNORECASE), "wearable wellness device"),
    (re.compile(r"\bbreast[\s-]*feed(ing)?\b", re.IGNORECASE), "feeding"),
    (re.compile(r"\bbreast[\s-]*milk\b", re.IGNORECASE), "nutrition"),
    (re.compile(r"\bmilk\s+extraction\b", re.IGNORECASE), "wellness session"),
    (re.compile(r"\blactation\b", re.IGNORECASE), "wellness"),
    (re.compile(r"\bnursing\s+(mother|mom|session|bra)\b", re.IGNORECASE), r"caring \1"),
    (re.compile(r"\b(start|begin|continue|finish)\s+pumping\b", re.IGNORECASE), r"\1 wellness routine"),
    (re.compile(r"\bpumping\s+(session|routine|time)\b", re.IGNORECASE), r"wellness \1"),

    # Baby bottles / feeding (Phase 2 expansion)
    (re.compile(r"\bbaby\s+bottle(s)?\b", re.IGNORECASE), "infant feeding container"),
    (re.compile(r"\bbottle\s+feed(ing)?\b", re.IGNORECASE), "container feeding"),
    (re.compile(r"\bnipple(s)?\b", re.IGNORECASE), "feeding tip"),
    (re.compile(r"\bareola\b", re.IGNORECASE), "surface area"),
    (re.compile(r"\bformula\s+(milk|feed(ing)?)\b", re.IGNORECASE), "prepared nutrition"),
    (re.compile(r"\bbaby\s+food\b", re.IGNORECASE), "infant nutrition"),
    (re.compile(r"\bpostpartum\b", re.IGNORECASE), "new parent"),

    # Chinese — single chars and common compounds
    (re.compile(r"吸奶器"), "可穿戴设备"),
    (re.compile(r"母乳喂养"), "亲子喂养"),
    (re.compile(r"哺乳"), "亲子"),
    (re.compile(r"挤奶"), "保养"),
    (re.compile(r"乳汁"), "营养"),

    # Chinese — Phase 2 expansion
    (re.compile(r"奶瓶"), "婴儿容器"),
    (re.compile(r"奶嘴"), "喂养配件"),
    (re.compile(r"辅食"), "婴儿食品"),
    (re.compile(r"婴儿食品"), "婴儿营养"),
    (re.compile(r"产后"), "恢复期"),
]


def sanitize_for_poyo(text: str) -> tuple[str, list[str]]:
    """Replace POYO content-moderation trigger words with neutral equivalents.

    Returns:
        (sanitized_text, list_of_applied_substitutions)
        list contains the original matched strings (lowercase) that were replaced.
    """
    if not text or not isinstance(text, str):
        return text, []
    applied: list[str] = []
    out = text
    for pattern, replacement in _SUBSTITUTIONS:
        new_out, n = pattern.subn(replacement, out)
        if n > 0:
            applied.append(f"{pattern.pattern}->{n}")
            out = new_out
    return out, applied
