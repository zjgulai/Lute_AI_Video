"""Test runner that mocks structlog for sandbox testing."""
import sys
import unittest.mock

# Mock structlog before any skill imports
sys.modules['structlog'] = unittest.mock.MagicMock()
sys.modules['structlog'].get_logger.return_value = unittest.mock.MagicMock()

import asyncio
from pathlib import Path
from src.skills.base import SkillResult
from src.skills.registry import SkillRegistry
from src.skills.character_identity import CharacterIdentitySkill
from src.skills.keyframe_images import KeyframeImagesSkill


# ──────────────────────────────────────────
# CharacterIdentitySkill tests
# ──────────────────────────────────────────

def _make_dummy_images(count: int = 3, tmp_path: Path | None = None) -> list[str]:
    import PIL.Image
    import tempfile
    if tmp_path is None:
        tmp_path = Path(tempfile.mkdtemp())
    paths = []
    for i in range(count):
        size = (640, 480) if i % 2 == 0 else (1280, 720)
        img = PIL.Image.new("RGB", size, color=(200 + i * 10, 150, 100))  # type: ignore[arg-type]
        fp = tmp_path / f"frame_{i:04d}.png"
        img.save(fp)
        paths.append(str(fp))
    return paths


def test_char_id_output():
    paths = _make_dummy_images(4)
    skill = CharacterIdentitySkill()
    result = asyncio.run(skill.execute({"frame_paths": paths}))
    assert result.success, f"execute failed: {result.error}"
    assert "reference_frames" in result.data
    assert "attributes" in result.data
    assert "face_count" in result.data["attributes"]
    assert "face_quality_score" in result.data["attributes"]
    assert len(result.data["reference_frames"]) <= 3
    print("PASS: test_char_id_output")


def test_char_id_validate():
    skill = CharacterIdentitySkill()
    assert len(skill.validate_params({})) > 0
    assert len(skill.validate_params({"frame_paths": []})) > 0
    assert len(skill.validate_params({"frame_paths": ["a.jpg"]})) == 0
    print("PASS: test_char_id_validate")


def test_char_id_fallback():
    skill = CharacterIdentitySkill()
    result = skill.fallback({"frame_paths": []})
    assert result.success
    assert "reference_frames" in result.data
    assert result.data.get("_fallback") is True
    print("PASS: test_char_id_fallback")


def test_char_id_registry():
    SkillRegistry.clear_global()
    skill = CharacterIdentitySkill()
    SkillRegistry.register(skill)
    paths = _make_dummy_images(3)
    result = asyncio.run(SkillRegistry().execute("character-identity", {"frame_paths": paths}))
    assert result.success
    assert "reference_frames" in result.data
    SkillRegistry.clear_global()
    print("PASS: test_char_id_registry")


# ──────────────────────────────────────────
# KeyframeImagesSkill tests
# ──────────────────────────────────────────

SAMPLE_STORYBOARD = {
    "script_id": "S1-001",
    "total_duration": 15.0,
    "shots": [
        {
            "id": 1, "start_time": 0.0, "end_time": 3.0,
            "shot_type": "CU", "visual": "Product close-up on clean white background",
            "text_overlay": "Meet X1 Pump", "camera": "Static",
        },
        {
            "id": 2, "start_time": 3.0, "end_time": 10.0,
            "shot_type": "MS", "visual": "Product being used in a modern kitchen",
            "text_overlay": "Key features", "camera": "Pan",
        },
        {
            "id": 3, "start_time": 10.0, "end_time": 15.0,
            "shot_type": "CU", "visual": "Product packaging with tagline",
            "text_overlay": "Get yours now", "camera": "Zoom",
        },
    ],
}


def mock_gpt_image_result(image_path="/tmp/mock_keyframe.png"):
    return SkillResult(
        success=True,
        data={
            "image_path": image_path,
            "image_url": "https://mock.url/image.png",
            "size": "1024x1792", "quality": "high",
            "prompt_used": "mock prompt", "image_id": "keyframe_000",
            "file_size_bytes": 4096, "is_stub": False,
            "verification": {"file_exists": True, "size_ok": True, "header_ok": True, "all_ok": True, "failures": []},
        },
    )


def test_keyframe_adds_path():
    skill = KeyframeImagesSkill()
    SkillRegistry.clear_global()
    SkillRegistry.register(skill)
    # Register a mock GPT-Image skill
    from src.skills.base import SkillCallable
    class MockGPTImageSkill(SkillCallable):
        name = "gpt-image-generate-skill"
        description = "Mock GPT image skill for testing"
        max_retries = 1
        async def execute(self, params):
            return mock_gpt_image_result()
        def validate_params(self, params):
            return []
        def validate_output(self, data):
            return []
        def fallback(self, params):
            return mock_gpt_image_result()
    mock_skill = MockGPTImageSkill()
    SkillRegistry.register(mock_skill)

    result = asyncio.run(skill.execute({"storyboard": SAMPLE_STORYBOARD}))
    assert result.success
    assert "shots" in result.data
    assert len(result.data["shots"]) == 3
    for i, shot in enumerate(result.data["shots"]):
        assert "keyframe_image_path" in shot, f"shot[{i}] missing keyframe_image_path"
    assert result.data.get("keyframes_generated") == 3
    SkillRegistry.clear_global()
    print("PASS: test_keyframe_adds_path")


def test_keyframe_fallback():
    skill = KeyframeImagesSkill()
    SkillRegistry.clear_global()
    SkillRegistry.register(skill)
    # Register a failing mock
    from src.skills.base import SkillCallable
    class FailingMockSkill(SkillCallable):
        name = "gpt-image-generate-skill"
        description = "Mock failing skill for testing"
        max_retries = 1
        async def execute(self, params):
            return SkillResult(success=False, error="API key missing")
        def validate_params(self, params):
            return []
        def validate_output(self, data):
            return []
        def fallback(self, params):
            return SkillResult(success=True, data={"image_path": "/tmp/fallback.png"})
    SkillRegistry.register(FailingMockSkill())

    result = asyncio.run(skill.execute({"storyboard": SAMPLE_STORYBOARD}))
    assert result.success
    for shot in result.data["shots"]:
        assert "keyframe_image_path" in shot
        assert shot["keyframe_image_path"] != ""
    SkillRegistry.clear_global()
    print("PASS: test_keyframe_fallback")


def test_keyframe_validate():
    skill = KeyframeImagesSkill()
    assert len(skill.validate_params({})) > 0
    assert len(skill.validate_params({"storyboard": {}})) > 0
    assert len(skill.validate_params({"storyboard": {"shots": [{"id": 1}]}})) == 0
    print("PASS: test_keyframe_validate")


def test_keyframe_compose_prompt():
    prompt = KeyframeImagesSkill._build_composition_prompt(
        visual="Product on marble countertop",
        camera="Dolly",
        shot_type="MS",
        identity_text="Color palette: #E8C9A0, #4A3728",
    )
    assert "Product on marble countertop" in prompt
    assert "Dolly" in prompt
    assert "MS" in prompt
    assert "E8C9A0" in prompt
    assert "cinematic lighting" in prompt
    print("PASS: test_keyframe_compose_prompt")


# ──────────────────────────────────────────
# Quality Gate Extension tests
# ──────────────────────────────────────────

from src.skills.media_quality_audit import MediaQualityAuditSkill


def test_qg_face_consistency():
    skill = MediaQualityAuditSkill()
    result = asyncio.run(skill.execute({
        "video_path": "/tmp/nonexistent_video.mp4",
        "audio_paths": [], "thumbnail_paths": [], "clip_paths": [],
        "expected_product_name": "Test Product",
        "expected_duration_seconds": 30, "expected_language": "en",
        "script_text": "", "thumbnail_prompts": [],
        "identity_card": {
            "reference_frames": ["/tmp/face_ref.jpg"],
            "attributes": {"face_count": 1, "face_quality_score": 0.85,
                          "dominant_colors": ["#E8C9A0"], "estimated_age_range": "25-35"},
        },
    }))
    assert result.success
    criteria_names = [c["name"] for c in result.data["criteria"]]
    assert "face_consistency" in criteria_names
    print("PASS: test_qg_face_consistency")


def test_qg_product_shape():
    skill = MediaQualityAuditSkill()
    result = asyncio.run(skill.execute({
        "video_path": "/tmp/nonexistent_video.mp4",
        "audio_paths": [], "thumbnail_paths": [], "clip_paths": [],
        "expected_product_name": "Test Product",
        "expected_duration_seconds": 30, "expected_language": "en",
        "script_text": "", "thumbnail_prompts": [],
        "product_reference_image": "/tmp/product_ref.jpg",
    }))
    assert result.success
    criteria_names = [c["name"] for c in result.data["criteria"]]
    assert "product_shape" in criteria_names
    print("PASS: test_qg_product_shape")


def test_qg_motion_smoothness():
    skill = MediaQualityAuditSkill()
    result = asyncio.run(skill.execute({
        "video_path": "/tmp/nonexistent_video.mp4",
        "audio_paths": [], "thumbnail_paths": [], "clip_paths": [],
        "expected_product_name": "Test Product",
        "expected_duration_seconds": 30, "expected_language": "en",
        "script_text": "", "thumbnail_prompts": [],
        "clip_video_paths": ["/tmp/clip_1.mp4"],
    }))
    assert result.success
    criteria_names = [c["name"] for c in result.data["criteria"]]
    assert "motion_smoothness" in criteria_names
    print("PASS: test_qg_motion_smoothness")


def test_qg_backward_compatible():
    skill = MediaQualityAuditSkill()
    result = asyncio.run(skill.execute({
        "video_path": "/tmp/nonexistent.mp4",
        "audio_paths": [], "thumbnail_paths": [], "clip_paths": [],
        "expected_product_name": "Product",
        "expected_duration_seconds": 30, "expected_language": "en",
        "script_text": "", "thumbnail_prompts": [],
    }))
    assert result.success
    criteria_names = [c["name"] for c in result.data["criteria"]]
    assert "final_video_present" in criteria_names
    assert "audio_coverage" in criteria_names
    assert "thumbnail_count" in criteria_names
    assert "clip_availability" in criteria_names
    assert "product_mention" in criteria_names
    assert "thumbnail_brand_alignment" in criteria_names
    assert "language_consistency" in criteria_names
    assert "face_consistency" not in criteria_names
    assert "product_shape" not in criteria_names
    assert "motion_smoothness" not in criteria_names
    print("PASS: test_qg_backward_compatible")


def test_qg_all_optional():
    skill = MediaQualityAuditSkill()
    result = asyncio.run(skill.execute({
        "video_path": "/tmp/nonexistent.mp4",
        "audio_paths": [], "thumbnail_paths": [], "clip_paths": [],
        "expected_product_name": "Product",
        "expected_duration_seconds": 30, "expected_language": "en",
        "script_text": "", "thumbnail_prompts": [],
        "identity_card": {"reference_frames": [],
            "attributes": {"face_count": 0, "face_quality_score": 0.0,
                          "dominant_colors": [], "estimated_age_range": ""}},
        "product_reference_image": "/tmp/product.png",
        "clip_video_paths": ["/tmp/clip1.mp4", "/tmp/clip2.mp4"],
    }))
    assert result.success
    criteria_names = [c["name"] for c in result.data["criteria"]]
    assert "face_consistency" in criteria_names
    assert "product_shape" in criteria_names
    assert "motion_smoothness" in criteria_names
    assert len(result.data["criteria"]) == 10, f"Expected 10, got {len(result.data['criteria'])}"
    print("PASS: test_qg_all_optional")


# ──────────────────────────────────────────
# Seedance skill import/validation test
# ──────────────────────────────────────────

def test_seedance_skill_imports():
    from src.skills.seedance_video_generate import SeedanceVideoGenerateSkill
    skill = SeedanceVideoGenerateSkill()
    assert skill.name == "seedance-video-generate-skill"
    # Test validate_params
    assert len(skill.validate_params({})) > 0
    assert len(skill.validate_params({"prompt": "test prompt for video generation"})) == 0
    # Test _extract_last_frame on non-existent file returns empty
    result = skill._extract_last_frame("/tmp/nonexistent.mp4")
    assert result == ""
    print("PASS: test_seedance_skill_imports")


# ──────────────────────────────────────────
# Run all tests
# ──────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_char_id_output,
        test_char_id_validate,
        test_char_id_fallback,
        test_char_id_registry,
        test_keyframe_adds_path,
        test_keyframe_fallback,
        test_keyframe_validate,
        test_keyframe_compose_prompt,
        test_qg_face_consistency,
        test_qg_product_shape,
        test_qg_motion_smoothness,
        test_qg_backward_compatible,
        test_qg_all_optional,
        test_seedance_skill_imports,
    ]
    passed = 0
    failed = 0
    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            print(f"FAIL: {test_fn.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed, {len(tests)} total")
