"""Regression test for F1 audit shape bug.

Bug: src/pipeline/s1_product_pipeline.py:369 used to read tts_audio output
as a list, but _step_tts_audio returns {"audio_paths": [...], "lyrics_paths": [...]}.
The unwrapped dict reached MediaQualityAuditSkill which fails its
isinstance(audio_paths, (list, tuple)) check and reports audio_coverage FAIL
even when audio files actually exist on disk.
"""

from __future__ import annotations

from typing import Any

import pytest


@pytest.mark.asyncio
async def test_s1_audit_unwraps_tts_audio_dict(monkeypatch, tmp_path):
    """audit step must extract audio_paths list from dict-shaped tts_audio output."""
    from src.pipeline.s1_product_pipeline import S1ProductDirectPipeline
    from src.skills.base import SkillResult
    from src.skills.registry import SkillRegistry

    # Touch fake audio files so audit's existence check would pass
    audio_files = []
    for i in range(2):
        p = tmp_path / f"seg_{i}.mp3"
        p.write_bytes(b"\x00" * 1024)
        audio_files.append(str(p))

    captured: dict[str, Any] = {}

    async def fake_execute(self, skill_name: str, params: dict[str, Any]):
        captured["skill"] = skill_name
        captured["params"] = params
        return SkillResult(success=True, data={"overall_status": "PASS", "criteria": []})

    monkeypatch.setattr(SkillRegistry, "execute", fake_execute)

    pipeline = S1ProductDirectPipeline()
    state = {
        "config": {
            "product_catalog": {"products": [{"name": "TestProduct"}]},
            "product_name": "TestProduct",
            "target_language": "en",
        },
        "errors": [],
        "media_synthesis_errors": [],
        "steps": {
            # tts_audio returns dict — same shape as _step_tts_audio (line 929)
            "tts_audio": {
                "edited": False,
                "edited_output": None,
                "output": {"audio_paths": audio_files, "lyrics_paths": []},
            },
            "thumbnail_images": {
                "edited": False,
                "edited_output": None,
                "output": [],
            },
            "seedance_clips": {
                "edited": False,
                "edited_output": None,
                "output": {
                    "clip_paths": [str(tmp_path / "clip.mp4")],
                    "clip_details": [{"is_stub": False}],
                },
            },
            "scripts": {"edited": False, "edited_output": None, "output": []},
            "thumbnail_prompts": {"edited": False, "edited_output": None, "output": []},
            "assemble_final": {
                "edited": False,
                "edited_output": None,
                "output": {"video_path": str(tmp_path / "final.mp4")},
            },
        },
    }

    # Make seedance clip path exist + non-stub so audit isn't short-circuited
    (tmp_path / "clip.mp4").write_bytes(b"\x00" * 2048)

    await pipeline.run_step("audit", state)

    assert captured["skill"] == "media-quality-audit-skill"
    audio_paths = captured["params"]["audio_paths"]
    assert isinstance(audio_paths, list), f"expected list, got {type(audio_paths).__name__}"
    assert audio_paths == audio_files, f"audio paths mismatch: {audio_paths}"
