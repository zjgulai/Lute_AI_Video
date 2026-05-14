"""AI candidate scoring for Expert Studio gates.

Provides scoring functions that evaluate candidate outputs using LLM-based
evaluation when available, with deterministic heuristic fallbacks when the
LLM is unavailable or the call fails.
"""

from __future__ import annotations

from typing import Any

import structlog

from src.tools.llm_client import llm

logger = structlog.get_logger()

# ── Baby Safety Sensitivity Keywords ──
_BABY_PRODUCT_KEYWORDS: list[str] = [
    "baby", "infant", "toddler", "newborn", "child", "children",
    "nursery", "feeding", "diaper", "breast pump", "bottle",
    "pacifier", "teether", "stroller", "crib", "carrier",
    "bib", "burp cloth", "swaddle", "monitor", "toy",
]

_BABY_SAFETY_POSITIVE_KEYWORDS: list[str] = [
    "safety", "safe", "caution", "warning", "supervised", "supervision",
    "age recommendation", "age appropriate", "not suitable for",
    "choking hazard", "small parts", "bpa free", "fda approved",
    "certified", "tested", "compliant", "meets safety standards",
    "cpsc", "astm", "iso", "en71", "follow instructions",
    "under adult", "parental guidance", "keep away",
]

_BABY_SAFETY_RISK_KEYWORDS: list[str] = [
    "unsupervised", "unattended", "sleep with", "co-sleep", "overnight",
    "prolonged", "excessive", "continuous use", "leave alone",
    "without supervision", "ignore warning", "disregard",
]


def _is_baby_product(product_catalog: dict[str, Any] | None) -> bool:
    """Detect if the product is baby/infant related from catalog data.

    Checks product name, category, tags, and description for baby-related terms.
    Returns True if any baby-related keyword is found.
    """
    if not product_catalog:
        return False

    text_sources: list[str] = []

    # Product name
    name = product_catalog.get("product_name") or product_catalog.get("name", "")
    if isinstance(name, str):
        text_sources.append(name)

    # Product category
    category = product_catalog.get("category", "")
    if isinstance(category, str):
        text_sources.append(category)

    # Tags
    tags = product_catalog.get("tags", [])
    if isinstance(tags, list):
        text_sources.extend(str(t) for t in tags if t)

    # Description
    description = product_catalog.get("description", "")
    if isinstance(description, str):
        text_sources.append(description)

    # Products list (nested catalog format)
    products = product_catalog.get("products", [])
    if isinstance(products, list):
        for p in products:
            if isinstance(p, dict):
                for key in ("name", "product_name", "category", "description"):
                    val = p.get(key, "")
                    if isinstance(val, str):
                        text_sources.append(val)
                for t in p.get("tags", []) if isinstance(p.get("tags"), list) else []:
                    if isinstance(t, str):
                        text_sources.append(t)

    combined = " ".join(text_sources).lower()
    return any(kw in combined for kw in _BABY_PRODUCT_KEYWORDS)


def _heuristic_baby_safety_sensitivity(script_text: str, is_baby_product: bool) -> float:
    """Heuristic scoring for baby safety sensitivity in script content.

    Returns 1.0 for non-baby products (dimension is neutral).
    For baby products, scores based on presence of safety-related content:
      - High score (0.8-1.0): adequate safety warnings and certifications
      - Medium score (0.4-0.7): some safety content but incomplete
      - Low score (0.0-0.3): missing safety info or contains risky advice
    """
    if not is_baby_product:
        return 1.0

    if not script_text:
        return 0.0  # Empty script for baby product = no safety info

    text_lower = script_text.lower()

    positive_hits = sum(1 for kw in _BABY_SAFETY_POSITIVE_KEYWORDS if kw in text_lower)
    risk_hits = sum(1 for kw in _BABY_SAFETY_RISK_KEYWORDS if kw in text_lower)

    # Risk keywords are strong negative signals — each one heavily penalizes
    if risk_hits > 0:
        return max(0.0, 0.3 - risk_hits * 0.1)

    # No safety content at all for a baby product is a significant gap
    if positive_hits == 0:
        return 0.3

    # Score increases with more safety coverage, capped at 1.0
    score = 0.5 + min(0.5, positive_hits * 0.08)
    return min(1.0, score)


async def score_candidate(
    step_name: str,
    candidate_data: dict[str, Any],
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Score a candidate using LLM evaluation or heuristics.

    Routes to the appropriate scoring function based on the step name.
    Tries LLM-based scoring first; falls back to heuristics on failure.

    Args:
        step_name: The pipeline step name (e.g., "scripts", "keyframe_images").
        candidate_data: The candidate output data to score.
        params: Optional scoring parameters (e.g., {"usps": [...], "platforms": [...]}).

    Returns:
        dict with keys:
            overall: float 0.0-1.0 (overall quality score)
            breakdown: dict of dimension scores
            explanation: str describing the scoring rationale
            heuristic: bool (True if heuristic fallback was used)
    """
    if params is None:
        params = {}

    # Route by step type
    if step_name in ("scripts", "remix_script"):
        return await _score_script_candidate(candidate_data, params)
    elif step_name == "character_identity":
        return await _score_character_identity_candidate(candidate_data, params)
    elif step_name == "vlog_strategy":
        return await _score_vlog_strategy_candidate(candidate_data, params)
    elif step_name == "keyframe_images":
        return await _score_keyframe_candidate(candidate_data, params)
    elif step_name == "seedance_clips":
        return await _score_clip_candidate(candidate_data, params)
    elif step_name == "assemble_final":
        return await _score_final_candidate(candidate_data, params)

    # Generic fallback for unknown step types
    return _heuristic_generic(candidate_data)


async def _score_script_candidate(script: dict[str, Any], params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Score a script candidate with LLM if available, else heuristics.

    Scoring dimensions:
        - text_quality (30%): Readability, hook quality, call-to-action
        - strategy_fit (25%): Alignment with strategy objectives
        - usp_coverage (20%): How many unique selling points are covered
        - platform_fit (15%): Suitability for target platforms
        - brand_tone (10%): Consistency with brand voice and tone
    """
    if params is None:
        params = {}

    usps = params.get("usps", [])
    brand_guidelines = params.get("brand_guidelines", "")
    product_catalog = params.get("product_catalog")

    # Try LLM-based scoring
    try:
        return await _llm_score_script(script, usps, brand_guidelines, product_catalog)
    except Exception as exc:
        logger.warning(
            "candidate_scorer: LLM scoring failed, using heuristics",
            step="scripts",
            error=str(exc)[:100],
        )
        return _heuristic_score_script(script, usps, product_catalog)


async def _llm_score_script(
    script: dict[str, Any],
    usps: list[str],
    brand_guidelines: str,
    product_catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Score a script candidate using the LLM."""
    script_text = _extract_script_text(script)
    usp_text = "\n".join(f"- {u}" for u in usps) if usps else "None provided"

    system_prompt = (
        "You are an expert video script evaluator. Score the following script "
        "on five dimensions from 0.0 to 1.0. Return ONLY valid JSON with keys: "
        "text_quality, strategy_fit, usp_coverage, platform_fit, brand_tone, "
        "overall (weighted average), and explanation. "
        "text_quality (30%% weight): readability, hook, CTA. "
        "strategy_fit (25%%): alignment with brand strategy. "
        "usp_coverage (20%%): how many USPs are mentioned. "
        "platform_fit (15%%): suitability for typical platforms. "
        "brand_tone (10%%): consistency with brand voice."
    )

    user_message = (
        f"Script text:\n{script_text}\n\n"
        f"Unique Selling Points:\n{usp_text}\n\n"
        f"Brand Guidelines:\n{brand_guidelines}\n\n"
        "Return JSON only."
    )

    result = await llm.invoke_json(system_prompt, user_message)

    overall = float(result.get("overall", result.get("text_quality", 0.75)))
    breakdown = {
        "text_quality": float(result.get("text_quality", 0.0)),
        "strategy_fit": float(result.get("strategy_fit", 0.0)),
        "usp_coverage": float(result.get("usp_coverage", 0.0)),
        "platform_fit": float(result.get("platform_fit", 0.0)),
        "brand_tone": float(result.get("brand_tone", 0.0)),
    }
    explanation = result.get("explanation", "LLM evaluation")

    # Apply baby-safety sensitivity penalty (no-op for non-baby products)
    is_baby = _is_baby_product(product_catalog)
    if is_baby:
        safety_score = _heuristic_baby_safety_sensitivity(script_text, True)
        breakdown["baby_safety"] = round(safety_score, 4)
        overall = overall * safety_score
        explanation = f"{explanation} | baby_safety={safety_score:.2f}"

    return {
        "overall": round(overall, 4),
        "breakdown": breakdown,
        "explanation": explanation,
        "heuristic": False,
    }


def _heuristic_score_script(
    script: dict[str, Any],
    usps: list[str],
    product_catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Score a script candidate using deterministic heuristics.

    Uses USP mention count, segment structure, word count, and hook presence.
    Defaults to 0.75 when heuristics cannot compute a meaningful score.
    """
    script_text = _extract_script_text(script)

    if not script_text or not script_text.strip():
        return {
            "overall": 0.0,
            "breakdown": {
                "text_quality": 0.0,
                "strategy_fit": 0.0,
                "usp_coverage": 0.0,
                "platform_fit": 0.5,
                "brand_tone": 0.5,
            },
            "explanation": "Empty script scored 0.0",
            "heuristic": True,
        }

    text_lower = script_text.lower()
    word_count = len(script_text.split())

    # USP coverage: count how many USPs appear in the script
    usp_score = 0.0
    if usps:
        mentioned = sum(1 for u in usps if u.lower() in text_lower)
        usp_score = min(1.0, mentioned / max(len(usps), 1))

    # Structure score: check for hook, solution/body, CTA segments
    has_hook = any(
        keyword in text_lower
        for keyword in ["imagine", "did you know", "have you ever", "hey", "look", "stop", "visual", "picture this"]
    )
    has_cta = any(
        keyword in text_lower
        for keyword in ["click", "buy now", "shop", "order", "get yours", "try it", "link in bio", "learn more", "sign up"]
    )
    structure_bonus = 0.0
    if has_hook:
        structure_bonus += 0.15
    if has_cta:
        structure_bonus += 0.15

    # Length score: 150-250 words is ideal for a 30s script
    length_score = 1.0
    if word_count < 80:
        length_score = word_count / 80.0
    elif word_count > 400:
        length_score = max(0.3, 1.0 - (word_count - 250) / 300.0)
    elif word_count > 250:
        length_score = max(0.7, 1.0 - (word_count - 250) / 200.0)

    text_quality = min(1.0, 0.5 + (structure_bonus * 1.5) + (length_score * 0.2))
    usp_coverage = usp_score
    strategy_fit = min(1.0, 0.6 + (usp_score * 0.3))
    platform_fit = 0.75  # generic default
    brand_tone = 0.75  # generic default

    overall = (
        text_quality * 0.30
        + strategy_fit * 0.25
        + usp_coverage * 0.20
        + platform_fit * 0.15
        + brand_tone * 0.10
    )

    breakdown = {
        "text_quality": round(text_quality, 4),
        "strategy_fit": round(strategy_fit, 4),
        "usp_coverage": round(usp_coverage, 4),
        "platform_fit": round(platform_fit, 4),
        "brand_tone": round(brand_tone, 4),
    }
    explanation = (
        f"Heuristic scoring: word_count={word_count}, "
        f"usp_mentions={usp_score:.0%}, "
        f"has_hook={has_hook}, has_cta={has_cta}"
    )

    # Apply baby-safety sensitivity penalty (no-op for non-baby products)
    is_baby = _is_baby_product(product_catalog)
    if is_baby:
        safety_score = _heuristic_baby_safety_sensitivity(script_text, True)
        breakdown["baby_safety"] = round(safety_score, 4)
        overall = overall * safety_score
        explanation = f"{explanation}, baby_safety={safety_score:.2f}"

    return {
        "overall": round(overall, 4),
        "breakdown": breakdown,
        "explanation": explanation,
        "heuristic": True,
    }


async def _score_keyframe_candidate(data: dict[str, Any], params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Score a keyframe image candidate with multi-dimensional heuristics.

    Dimensions: composition (30%), lighting (20%), product visibility (25%), style consistency (25%).
    When LLM is unavailable, scores based on prompt keywords rather than a fixed default.
    """
    prompt = str(data.get("prompt", "")).lower()
    if not prompt:
        return _heuristic_generic(data, default=0.50)

    composition_score = 1.0 if any(kw in prompt for kw in ["center", "rule of thirds", "close-up", "framed"]) else 0.6
    lighting_score = 1.0 if any(kw in prompt for kw in ["soft", "natural", "studio", "warm", "bright"]) else 0.6
    product_score = 1.0 if any(kw in prompt for kw in ["product", "device", "item", "hero shot"]) else 0.5
    style_score = 0.8  # baseline — LLM scoring would refine this

    overall = composition_score * 0.30 + lighting_score * 0.20 + product_score * 0.25 + style_score * 0.25
    return {
        "overall": round(overall, 4),
        "breakdown": {
            "composition": round(composition_score, 4),
            "lighting": round(lighting_score, 4),
            "product_visibility": round(product_score, 4),
            "style_consistency": round(style_score, 4),
        },
        "explanation": "Heuristic keyframe scoring based on prompt keywords",
        "heuristic": True,
    }


async def _score_clip_candidate(data: dict[str, Any], params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Score a video clip candidate with multi-dimensional heuristics.

    Dimensions: prompt quality (30%), duration match (25%), file presence (25%), continuity (20%).
    """
    prompt = str(data.get("prompt", "")).lower()
    duration = data.get("duration", 0)
    target_duration = data.get("target_duration", duration)
    file_size = data.get("file_size", 0)

    # Prompt quality: presence of motion / action keywords
    motion_keywords = ["motion", "movement", "tracking", "pan", "zoom", "rotate", "fade"]
    prompt_score = 1.0 if any(kw in prompt for kw in motion_keywords) else 0.6
    if not prompt:
        prompt_score = 0.4

    # Duration match: within 20% of target
    if target_duration > 0:
        ratio = min(duration, target_duration) / max(duration, target_duration, 1)
        duration_score = 0.5 + 0.5 * ratio
    else:
        duration_score = 0.6

    # File presence: non-zero file size indicates real generation
    file_score = 1.0 if file_size > 1024 else 0.3

    # Continuity: presence of continuity frame reference
    continuity_score = 1.0 if data.get("continuity_frame") else 0.6

    overall = prompt_score * 0.30 + duration_score * 0.25 + file_score * 0.25 + continuity_score * 0.20
    return {
        "overall": round(overall, 4),
        "breakdown": {
            "prompt_quality": round(prompt_score, 4),
            "duration_match": round(duration_score, 4),
            "file_presence": round(file_score, 4),
            "continuity": round(continuity_score, 4),
        },
        "explanation": f"Heuristic clip scoring: prompt={prompt_score:.2f}, duration={duration_score:.2f}, file={file_score:.2f}",
        "heuristic": True,
    }


async def _score_character_identity_candidate(data: dict[str, Any], params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Score a character identity candidate for S3 Influencer Remix.

    Dimensions: completeness (40%), consistency (30%), influence fit (30%).
    """
    name = str(data.get("name", "")).strip()
    bio = str(data.get("bio", "")).strip()
    style = str(data.get("presentation_style", "")).strip()
    visuals = data.get("visual_identity", {})

    completeness = 0.0
    if name:
        completeness += 0.3
    if bio and len(bio) > 20:
        completeness += 0.3
    if style:
        completeness += 0.2
    if visuals and isinstance(visuals, dict) and any(visuals.values()):
        completeness += 0.2

    consistency = 0.75
    if bio and name.lower() in bio.lower():
        consistency = 0.9

    influence_fit = 0.75
    influencer_keywords = ["authentic", "relatable", "trust", "experience", "mom", "parent"]
    if bio:
        bio_lower = bio.lower()
        matched = sum(1 for kw in influencer_keywords if kw in bio_lower)
        influence_fit = min(1.0, 0.5 + matched * 0.1)

    overall = completeness * 0.40 + consistency * 0.30 + influence_fit * 0.30
    return {
        "overall": round(overall, 4),
        "breakdown": {
            "completeness": round(completeness, 4),
            "consistency": round(consistency, 4),
            "influence_fit": round(influence_fit, 4),
        },
        "explanation": f"Character identity: completeness={completeness:.2f}, consistency={consistency:.2f}, influence_fit={influence_fit:.2f}",
        "heuristic": True,
    }


async def _score_vlog_strategy_candidate(data: dict[str, Any], params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Score a VLOG strategy candidate for S5 Brand VLOG.

    Dimensions: structure (35%), hook quality (30%), brand alignment (20%), platform fit (15%).
    """
    title = str(data.get("title", "")).strip()
    hook = str(data.get("hook", "")).strip()
    segments = data.get("segments", [])
    if isinstance(segments, list):
        segment_count = len(segments)
    else:
        segment_count = 0

    structure = 0.0
    if title:
        structure += 0.2
    if hook:
        structure += 0.2
    structure += min(0.4, segment_count * 0.1)

    hook_quality = 0.5
    hook_keywords = ["why", "how", "secret", "truth", "behind", "day", "life", "journey"]
    if hook:
        hook_lower = hook.lower()
        matched = sum(1 for kw in hook_keywords if kw in hook_lower)
        hook_quality = min(1.0, 0.4 + matched * 0.15)
        if len(hook) > 50:
            hook_quality = min(1.0, hook_quality + 0.1)

    brand_alignment = 0.7
    if params and "brand_guidelines" in params:
        brand_guidelines = str(params["brand_guidelines"]).lower()
        if title.lower() in brand_guidelines or any(kw in title.lower() for kw in brand_guidelines.split()[:5]):
            brand_alignment = 0.85

    platform_fit = 0.75
    platform_keywords = ["youtube", "tiktok", "instagram", "reels", "shorts"]
    content_str = f"{title} {hook}".lower()
    matched = sum(1 for kw in platform_keywords if kw in content_str)
    if matched > 0:
        platform_fit = min(1.0, 0.6 + matched * 0.1)

    overall = structure * 0.35 + hook_quality * 0.30 + brand_alignment * 0.20 + platform_fit * 0.15
    return {
        "overall": round(overall, 4),
        "breakdown": {
            "structure": round(structure, 4),
            "hook_quality": round(hook_quality, 4),
            "brand_alignment": round(brand_alignment, 4),
            "platform_fit": round(platform_fit, 4),
        },
        "explanation": f"VLOG strategy: structure={structure:.2f}, hook={hook_quality:.2f}, brand={brand_alignment:.2f}, platform={platform_fit:.2f}",
        "heuristic": True,
    }


async def _score_final_candidate(data: dict[str, Any], params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Score a final assembled video candidate with multi-dimensional heuristics.

    Dimensions: duration compliance (30%), audio present (25%), thumbnail present (25%), file valid (20%).
    """
    duration = data.get("duration", 0)
    target_duration = data.get("target_duration", 0)
    has_audio = bool(data.get("audio_path") or data.get("audio_paths"))
    has_thumbnail = bool(data.get("thumbnail_path") or data.get("thumbnail_paths"))
    file_size = data.get("file_size", 0)

    # Duration compliance: within 10% of target
    if target_duration > 0:
        diff = abs(duration - target_duration) / target_duration
        duration_score = max(0.0, 1.0 - diff * 5)
    else:
        duration_score = 0.6 if duration > 0 else 0.0

    audio_score = 1.0 if has_audio else 0.3
    thumbnail_score = 1.0 if has_thumbnail else 0.3
    file_score = 1.0 if file_size > 1024 * 1024 else 0.5  # > 1MB = real video

    overall = duration_score * 0.30 + audio_score * 0.25 + thumbnail_score * 0.25 + file_score * 0.20
    return {
        "overall": round(overall, 4),
        "breakdown": {
            "duration_compliance": round(duration_score, 4),
            "audio_present": round(audio_score, 4),
            "thumbnail_present": round(thumbnail_score, 4),
            "file_valid": round(file_score, 4),
        },
        "explanation": f"Heuristic final scoring: duration={duration_score:.2f}, audio={audio_score:.2f}, thumb={thumbnail_score:.2f}, file={file_score:.2f}",
        "heuristic": True,
    }


def _heuristic_generic(data: dict[str, Any], default: float = 0.75) -> dict[str, Any]:
    """Generic heuristic scoring for non-text candidates.

    Returns a default score with a heuristic flag. Used when no specific
    scoring logic is available for a step type.
    """
    has_content = bool(data) and any(
        v is not None and v != "" and v != []
        for v in data.values()
    )

    if not has_content:
        return {
            "overall": 0.0,
            "breakdown": {"presence": 0.0},
            "explanation": "No content present",
            "heuristic": True,
        }

    return {
        "overall": default,
        "breakdown": {"presence": default},
        "explanation": f"Generic heuristic score ({default})",
        "heuristic": True,
    }


def _extract_script_text(script: dict[str, Any]) -> str:
    """Extract human-readable text from a script dict.

    Handles various script output formats returned by the pipeline.
    """
    if not script:
        return ""

    # Direct text field
    if isinstance(script, str):
        return script

    # Nested text under common keys
    for key in ("text", "body", "content", "script_text", "narration", "description"):
        value = script.get(key)
        if value and isinstance(value, str):
            return value

    # List of segments (hook / solution / cta)
    segments = script.get("segments") or script.get("scenes") or []
    if segments and isinstance(segments, list):
        texts = []
        for seg in segments:
            if isinstance(seg, str):
                texts.append(seg)
            elif isinstance(seg, dict):
                for seg_key in ("text", "content", "narration", "dialogue", "voiceover"):
                    seg_val = seg.get(seg_key)
                    if seg_val and isinstance(seg_val, str):
                        texts.append(seg_val)
                        break
        if texts:
            return "\n".join(texts)

    # Fallback: dump the whole dict as string
    import json
    try:
        return json.dumps(script, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(script)
