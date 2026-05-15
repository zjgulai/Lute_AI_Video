"""Sprint 4 P4-3: AI non-determinism test framework — example tests.

This file defines TWO example tests demonstrating the llm_stability and
media_stability pytest markers. Both default-skip unless API keys are
present, so CI runs them as no-ops; manual triggers via:

    pytest -m llm_stability tests/test_ai_stability_markers.py
    pytest -m media_stability tests/test_ai_stability_markers.py

Pattern:
- N sample size (default 3 — keep small for cost control)
- Assert structural stability (schema keys, field types) NOT exact values
- Optional: assert statistical stability (variance < threshold)
- Each sample call costs real API money — keep N tight and add @pytest.mark
  so opt-in is explicit.

Future expansion:
- Add more cases under llm_stability for script-writer / strategy / etc.
- Add more cases under media_stability for keyframe-images / seedance-clips.
- Wire into CI as a nightly job with budget cap.
"""

from __future__ import annotations

import os

import pytest


def _has_llm_credentials() -> bool:
    """True iff at least one real LLM key is in env (DeepSeek or OpenAI)."""
    return bool(os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY"))


def _has_poyo_credentials() -> bool:
    """True iff POYO_API_KEY is in env."""
    return bool(os.environ.get("POYO_API_KEY"))


# Sample size for stability runs. Keep small — each sample is a paid API call.
_STABILITY_N = 3


@pytest.mark.llm_stability
@pytest.mark.skipif(not _has_llm_credentials(), reason="no LLM API key in env")
@pytest.mark.asyncio
async def test_llm_invoke_json_schema_stability():
    """Schema stability: same system+user prompt across N runs → same keys
    + same field types. Values can vary (LLM is non-deterministic) but
    structure must hold or downstream parsers break."""
    from src.tools.llm_client import LLMClient

    llm = LLMClient(timeout=30.0)
    system = "You are a JSON-only response generator."
    user = (
        "Return a JSON object describing a hypothetical product. "
        "Keys MUST be exactly: name (str), price (number), tags (list of str). "
        "Return ONLY the JSON, no markdown."
    )

    samples: list[dict] = []
    for _ in range(_STABILITY_N):
        result = await llm.invoke_json(system, user)
        samples.append(result)

    # Schema invariant: same keys appear in all samples
    key_sets = [set(s.keys()) for s in samples]
    assert all(ks == key_sets[0] for ks in key_sets), (
        f"LLM returned divergent key sets across runs: {key_sets}"
    )
    # Field type invariant: 'name' is always str, 'tags' always list
    for s in samples:
        assert isinstance(s.get("name"), str), f"name not str: {s}"
        assert isinstance(s.get("tags"), list), f"tags not list: {s}"


@pytest.mark.media_stability
@pytest.mark.skipif(not _has_poyo_credentials(), reason="no POYO_API_KEY in env")
@pytest.mark.asyncio
async def test_seedance_duration_stability():
    """Duration stability: same prompt + duration request across N runs →
    actual returned duration within ±15% of requested. Beyond that band
    indicates Seedance is silently truncating or padding clips, breaking
    downstream concatenation math."""
    from src.tools.seedance_client import SeedanceClient

    client = SeedanceClient()
    prompt = "A cup of coffee on a table, soft morning light, no people."
    requested = 5
    tolerance = 0.15

    durations: list[float] = []
    for _ in range(_STABILITY_N):
        result = await client.text_to_video(
            prompt=prompt,
            duration=requested,
            resolution="720p",
        )
        actual = float(result.get("duration_seconds", 0))
        durations.append(actual)

    assert all(d > 0 for d in durations), f"All-zero durations indicate stub mode: {durations}"
    for d in durations:
        deviation = abs(d - requested) / requested
        assert deviation <= tolerance, (
            f"Duration {d}s deviates >{tolerance:.0%} from requested {requested}s "
            f"(all: {durations})"
        )
