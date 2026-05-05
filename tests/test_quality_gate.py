"""Tests for the extended media quality audit — quality gate checks."""

import asyncio
from pathlib import Path
from unittest.mock import patch

from src.skills.media_quality_audit import MediaQualityAuditSkill
from src.skills.base import SkillResult
from src.skills.registry import SkillRegistry


def test_quality_gate_face_consistency_check_in_criteria():
    """Verify that when identity_card is provided, the face_consistency criterion appears."""
    skill = MediaQualityAuditSkill()

    # Run with identity_card but without a real video (to test it doesn't crash)
    # The video doesn't exist, so it should produce a FAIL/WARN entry for face_consistency
    result = asyncio.run(skill.execute({
        "video_path": "/tmp/nonexistent_video.mp4",
        "audio_paths": [],
        "thumbnail_paths": [],
        "clip_paths": [],
        "expected_product_name": "Test Product",
        "expected_duration_seconds": 30,
        "expected_language": "en",
        "script_text": "Test script about Test Product",
        "thumbnail_prompts": [],
        "identity_card": {
            "reference_frames": ["/tmp/face_ref.jpg"],
            "attributes": {
                "face_count": 1,
                "face_quality_score": 0.85,
                "dominant_colors": ["#E8C9A0"],
                "estimated_age_range": "25-35",
            },
        },
    }))

    assert result.success, f"execute failed: {result.error}"
    assert result.data is not None
    assert "criteria" in result.data

    criteria_names = [c["name"] for c in result.data["criteria"]]
    assert "face_consistency" in criteria_names, \
        f"Expected 'face_consistency' in criteria, got: {criteria_names}"


def test_quality_gate_product_shape_check_in_criteria():
    """Verify that when product_reference_image is provided, product_shape appears."""
    skill = MediaQualityAuditSkill()

    result = asyncio.run(skill.execute({
        "video_path": "/tmp/nonexistent_video.mp4",
        "audio_paths": [],
        "thumbnail_paths": [],
        "clip_paths": [],
        "expected_product_name": "Test Product",
        "expected_duration_seconds": 30,
        "expected_language": "en",
        "script_text": "",
        "thumbnail_prompts": [],
        "product_reference_image": "/tmp/product_ref.jpg",
    }))

    assert result.success
    criteria_names = [c["name"] for c in result.data["criteria"]]
    assert "product_shape" in criteria_names, \
        f"Expected 'product_shape' in criteria, got: {criteria_names}"


def test_quality_gate_motion_smoothness_check_in_criteria():
    """Verify that motion_smoothness appears when clip_video_paths is provided."""
    skill = MediaQualityAuditSkill()

    result = asyncio.run(skill.execute({
        "video_path": "/tmp/nonexistent_video.mp4",
        "audio_paths": [],
        "thumbnail_paths": [],
        "clip_paths": [],
        "expected_product_name": "Test Product",
        "expected_duration_seconds": 30,
        "expected_language": "en",
        "script_text": "",
        "thumbnail_prompts": [],
        "clip_video_paths": ["/tmp/clip_1.mp4"],
    }))

    assert result.success
    criteria_names = [c["name"] for c in result.data["criteria"]]
    assert "motion_smoothness" in criteria_names, \
        f"Expected 'motion_smoothness' in criteria, got: {criteria_names}"


def test_quality_gate_backward_compatible():
    """Verify existing checks still work without new optional params."""
    skill = MediaQualityAuditSkill()

    # Call with the same params as before (no identity_card, product_ref, clip_videos)
    result = asyncio.run(skill.execute({
        "video_path": "/tmp/nonexistent.mp4",
        "audio_paths": [],
        "thumbnail_paths": [],
        "clip_paths": [],
        "expected_product_name": "Product",
        "expected_duration_seconds": 30,
        "expected_language": "en",
        "script_text": "",
        "thumbnail_prompts": [],
    }))

    assert result.success
    criteria_names = [c["name"] for c in result.data["criteria"]]

    # Original criteria must still be present
    assert "final_video_present" in criteria_names
    assert "audio_coverage" in criteria_names
    assert "thumbnail_count" in criteria_names
    assert "clip_availability" in criteria_names
    assert "product_mention" in criteria_names
    assert "thumbnail_brand_alignment" in criteria_names
    assert "language_consistency" in criteria_names

    # New checks should NOT be present (optional, no input given)
    assert "face_consistency" not in criteria_names, \
        "face_consistency should NOT appear when identity_card not provided"
    assert "product_shape" not in criteria_names, \
        "product_shape should NOT appear when product_reference_image not provided"
    assert "motion_smoothness" not in criteria_names, \
        "motion_smoothness should NOT appear when clip_video_paths not provided"


def test_quality_gate_via_registry():
    """Verify the skill is registered and callable via SkillRegistry."""
    SkillRegistry.clear()
    skill = MediaQualityAuditSkill()
    SkillRegistry.register(skill)

    result = asyncio.run(SkillRegistry.execute("media-quality-audit-skill", {
        "video_path": "/tmp/nonexistent.mp4",
        "audio_paths": [],
        "thumbnail_paths": [],
        "clip_paths": [],
        "expected_product_name": "Product",
        "expected_duration_seconds": 30,
        "expected_language": "en",
        "script_text": "",
        "thumbnail_prompts": [],
        "identity_card": {
            "reference_frames": [],
            "attributes": {"face_count": 0, "face_quality_score": 0.0,
                          "dominant_colors": [], "estimated_age_range": ""},
        },
    }))

    assert result.success
    assert result.data is not None
    criteria_names = [c["name"] for c in result.data["criteria"]]
    assert "face_consistency" in criteria_names

    SkillRegistry.clear()


def test_quality_gate_all_optional_checks_together():
    """Verify all three new checks appear when all inputs provided."""
    skill = MediaQualityAuditSkill()

    result = asyncio.run(skill.execute({
        "video_path": "/tmp/nonexistent.mp4",
        "audio_paths": [],
        "thumbnail_paths": [],
        "clip_paths": [],
        "expected_product_name": "Product",
        "expected_duration_seconds": 30,
        "expected_language": "en",
        "script_text": "",
        "thumbnail_prompts": [],
        "identity_card": {
            "reference_frames": [],
            "attributes": {"face_count": 0, "face_quality_score": 0.0,
                          "dominant_colors": [], "estimated_age_range": ""},
        },
        "product_reference_image": "/tmp/product.png",
        "clip_video_paths": ["/tmp/clip1.mp4", "/tmp/clip2.mp4"],
    }))

    assert result.success
    criteria_names = [c["name"] for c in result.data["criteria"]]
    assert "face_consistency" in criteria_names
    assert "product_shape" in criteria_names
    assert "motion_smoothness" in criteria_names

    # Total should be 7 original + 3 new = 10
    assert len(result.data["criteria"]) == 10, \
        f"Expected 10 criteria (7 old + 3 new), got {len(result.data['criteria'])}: {criteria_names}"


if __name__ == "__main__":
    test_quality_gate_face_consistency_check_in_criteria()
    test_quality_gate_product_shape_check_in_criteria()
    test_quality_gate_motion_smoothness_check_in_criteria()
    test_quality_gate_backward_compatible()
    test_quality_gate_via_registry()
    test_quality_gate_all_optional_checks_together()
    print("All quality_gate tests passed.")
