"""AI candidate scoring for Expert Studio gates.

Provides scoring functions that evaluate candidate outputs using LLM-based
evaluation when available, with deterministic heuristic fallbacks when the
LLM is unavailable or the call fails.
"""

from __future__ import annotations

import structlog

from src.tools.llm_client import llm

logger = structlog.get_logger()


async def score_candidate(
    step_name: str,
    candidate_data: dict,
    params: dict | None = None,
) -> dict:
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
    if step_name == "scripts":
        return await _score_script_candidate(candidate_data, params)
    elif step_name == "keyframe_images":
        return await _score_keyframe_candidate(candidate_data, params)
    elif step_name == "seedance_clips":
        return await _score_clip_candidate(candidate_data, params)
    elif step_name == "assemble_final":
        return await _score_final_candidate(candidate_data, params)

    # Generic fallback for unknown step types
    return _heuristic_generic(candidate_data)


async def _score_script_candidate(script: dict, params: dict | None = None) -> dict:
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

    # Try LLM-based scoring
    try:
        return await _llm_score_script(script, usps, brand_guidelines)
    except Exception as exc:
        logger.warning(
            "candidate_scorer: LLM scoring failed, using heuristics",
            step="scripts",
            error=str(exc)[:100],
        )
        return _heuristic_score_script(script, usps)


async def _llm_score_script(script: dict, usps: list[str], brand_guidelines: str) -> dict:
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

    return {
        "overall": overall,
        "breakdown": breakdown,
        "explanation": explanation,
        "heuristic": False,
    }


def _heuristic_score_script(script: dict, usps: list[str]) -> dict:
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

    return {
        "overall": round(overall, 4),
        "breakdown": {
            "text_quality": round(text_quality, 4),
            "strategy_fit": round(strategy_fit, 4),
            "usp_coverage": round(usp_coverage, 4),
            "platform_fit": round(platform_fit, 4),
            "brand_tone": round(brand_tone, 4),
        },
        "explanation": (
            f"Heuristic scoring: word_count={word_count}, "
            f"usp_mentions={usp_score:.0%}, "
            f"has_hook={has_hook}, has_cta={has_cta}"
        ),
        "heuristic": True,
    }


async def _score_keyframe_candidate(data: dict, params: dict | None = None) -> dict:
    """Score a keyframe image candidate."""
    return _heuristic_generic(data, default=0.75)


async def _score_clip_candidate(data: dict, params: dict | None = None) -> dict:
    """Score a video clip candidate."""
    return _heuristic_generic(data, default=0.75)


async def _score_final_candidate(data: dict, params: dict | None = None) -> dict:
    """Score a final assembled video candidate."""
    return _heuristic_generic(data, default=0.80)


def _heuristic_generic(data: dict, default: float = 0.75) -> dict:
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


def _extract_script_text(script: dict) -> str:
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
