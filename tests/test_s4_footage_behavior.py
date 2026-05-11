"""Tests confirming current S4 footage_assets behavior.

S4 (Live Shoot) accepts a footage_assets list in submit body, but the
v0.2.4 implementation only uses each asset's filename as a text prompt
reference (e.g. \"@material 'pump-footage.mp4'\") inside seedance prompts.
The actual video content / frames of uploaded footage are NOT used as
image-to-video conditioning.

This is by design for now — true frame-conditioned generation requires
either Seedance image-to-video API (not available in current connector)
or pre-extracting frames + passing as keyframes (architectural change).

Tests pin the current behavior so any change is intentional.

P1-6 of NEXT-STEPS-2026-05-11.md: documents this gap. Closing the loop
(video content -> generation conditioning) is Sprint 2+ scope.
"""
from __future__ import annotations


def test_s4_uses_filename_as_prompt_reference_not_frames():
    """When footage_assets is provided, S4 builds @material '<filename>'
    text references inside seedance prompts. It does NOT extract frames or
    pass video bytes as image-to-video conditioning."""
    import inspect

    from src.pipeline.s4_live_shoot_pipeline import S4LiveShootPipeline  # noqa: F401
    src = inspect.getsource(S4LiveShootPipeline)
    assert "footage_assets" in src
    assert "@material" in src, "S4 pipeline still uses @material prompt convention"
    assert "image-to-video" not in src.lower(), (
        "If image-to-video conditioning is added, update this test + "
        "NEXT-STEPS P1-6 to reflect closure of the loop"
    )


def test_s4_keyframe_skill_does_not_accept_user_upload_path():
    """keyframe_images skill takes a storyboard dict and generates new
    keyframes via GPT-Image — it does NOT accept a user-uploaded image
    path as a reference. This is the loop that's open.

    If keyframe-images grows an `input_reference_path` parameter or
    similar, update NEXT-STEPS P1-6 backlog accordingly."""
    import inspect

    from src.skills.keyframe_images import KeyframeImagesSkill
    src = inspect.getsource(KeyframeImagesSkill)
    assert "input_reference_path" not in src
    assert "user_upload" not in src
    assert "footage_asset" not in src
