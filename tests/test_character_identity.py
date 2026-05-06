"""Tests for CharacterIdentitySkill — frame face detection."""

from pathlib import Path

from src.skills.character_identity import CharacterIdentitySkill
from src.skills.registry import SkillRegistry


def _make_dummy_images(count: int = 3, tmp_path: Path | None = None) -> list[str]:
    """Create dummy frame images for testing."""
    import PIL.Image

    if tmp_path is None:
        import tempfile
        tmp_path = Path(tempfile.mkdtemp())

    paths = []
    for i in range(count):
        size = (640, 480) if i % 2 == 0 else (1280, 720)
        img = PIL.Image.new("RGB", size, color=(200 + i * 10, 150, 100))
        fp = tmp_path / f"frame_{i:04d}.png"
        img.save(fp)
        paths.append(str(fp))
    return paths


def test_character_identity_output_structure():
    """Verify that CharacterIdentitySkill returns expected keys."""
    paths = _make_dummy_images(4)
    skill = CharacterIdentitySkill()
    params = {"frame_paths": paths}

    # Run synchronously via asyncio
    import asyncio
    result = asyncio.run(skill.execute(params))

    assert result.success, f"execute failed: {result.error}"
    assert result.data is not None
    assert "reference_frames" in result.data, "missing reference_frames"
    assert "attributes" in result.data, "missing attributes"
    assert "face_count" in result.data["attributes"]
    assert "face_quality_score" in result.data["attributes"]
    assert "dominant_colors" in result.data["attributes"]
    assert "estimated_age_range" in result.data["attributes"]

    # reference_frames should have at most 3 entries
    assert len(result.data["reference_frames"]) <= 3


def test_character_identity_validate_params():
    """Verify validate_params catches missing frame_paths."""
    skill = CharacterIdentitySkill()

    errors = skill.validate_params({})
    assert len(errors) > 0
    assert any("frame_paths" in e for e in errors)

    errors = skill.validate_params({"frame_paths": []})
    assert len(errors) > 0

    errors = skill.validate_params({"frame_paths": ["a.jpg", "b.jpg"]})
    assert len(errors) == 0


def test_character_identity_fallback():
    """Verify fallback produces valid output."""
    skill = CharacterIdentitySkill()
    result = skill.fallback({"frame_paths": []})

    assert result.success
    assert "reference_frames" in result.data
    assert "attributes" in result.data
    assert result.data.get("_fallback") is True


def test_character_identity_via_registry():
    """Verify the skill is auto-registered and callable via SkillRegistry."""
    # Clean slate
    SkillRegistry.clear_global()

    # Re-register (as the module __init__ would do)
    skill = CharacterIdentitySkill()
    SkillRegistry.register(skill)

    import asyncio
    paths = _make_dummy_images(3)
    result = asyncio.run(SkillRegistry().execute("character-identity", {
        "frame_paths": paths,
    }))

    assert result.success
    assert "reference_frames" in result.data
    assert "attributes" in result.data

    SkillRegistry.clear_global()


if __name__ == "__main__":
    # Manual run
    test_character_identity_output_structure()
    test_character_identity_validate_params()
    test_character_identity_fallback()
    test_character_identity_via_registry()
    print("All character_identity tests passed.")
