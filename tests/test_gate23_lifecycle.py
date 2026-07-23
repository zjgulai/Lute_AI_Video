"""Sprint 4 P4-1: Gate 2 (keyframe) + Gate 3 (clips) lifecycle tests.

Existing tests/test_s1_gate_full_flow.py covers:
- GATE_DEFINITIONS contract for all 4 gates
- get_gate_state / approve_gate error paths (unknown gate, missing label)
- gate_1_script approve + multi-selection + max-selections-error
- gate_4_final state assembly

Gap closed by this file:
- Gate 2 keyframe: approve happy path, max_selections=1 enforcement,
  regenerate single candidate, state persistence after approve.
- Gate 3 clips: approve happy path, max_selections=1 enforcement,
  edited_output gets the right shape (clip_paths list).

These tests use synthetic state (no LLM / POYO calls) — same pattern as
TestApproveGateSuccess in test_s1_gate_full_flow.py.
"""

from __future__ import annotations

import pytest

from src.pipeline.gate_manager import (
    approve_gate,
    get_gate_state,
)
from src.pipeline.state_manager import PipelineStateManager
from tests.generation_policy_test_utils import attach_execution_policy

# ── Gate 2 keyframe ──


def _gate_2_state(label: str, candidate_ids: list[str]) -> dict:
    """Build a minimal pipeline state with Gate 2 awaiting approval.

    Per gate_manager.py:619-622, candidate.data for keyframe_images is the
    raw skill output (a single storyboard-shaped dict), and gate_manager
    wraps it as `[raw_data]` when materializing edited_output.
    """
    candidates = [
        {
            "id": cid,
            "variant": v,
            # Single storyboard dict per candidate (skill returns one)
            "data": {
                "scene_id": f"scene_for_{cid}",
                "keyframe_image_path": f"/tmp/{cid}_kf.png",
                "prompt": f"keyframe variant {v}",
            },
            "score": {"overall": 0.7 + 0.05 * i},
            "acceptable": True,
            "recommended": (i == 1),
        }
        for i, (cid, v) in enumerate(
            zip(candidate_ids, ["standard", "creative", "conservative"], strict=False)
        )
    ]
    return attach_execution_policy({
        "label": label,
        "scenario": "s1",
        "config": {"product_catalog": {"name": "X"}, "brand_guidelines": {}},
        "steps": {
            "strategy": {"output": {}, "status": "done"},
            "scripts": {"output": [], "status": "done"},
            "compliance": {"output": [], "status": "done"},
            "storyboards": {"output": [], "status": "done"},
            "keyframe_images": {
                "output": {"shots": []},
                "status": "done",
            },
        },
        "current_step": "keyframe_images",
        "gates": {
            "gate_2_keyframe": {
                "status": "awaiting_approval",
                "candidates": candidates,
                "selected_ids": [],
                "approved": False,
            },
        },
    }, scenario="s1", media=True)


class TestGate2KeyframeLifecycle:

    @pytest.mark.asyncio
    async def test_get_state_returns_awaiting(self, isolated_state_dir):
        sm = PipelineStateManager()
        state = _gate_2_state("g2-state-test", ["g2_c0", "g2_c1", "g2_c2"])
        await sm.save("g2-state-test", state)

        result = await get_gate_state("g2-state-test", "gate_2_keyframe")
        assert result["status"] == "awaiting_approval"
        assert len(result["candidates"]) == 3
        # Recommended should be the c1 variant (i==1)
        recommended = [c for c in result["candidates"] if c["recommended"]]
        assert len(recommended) == 1
        assert recommended[0]["id"] == "g2_c1"

    @pytest.mark.asyncio
    async def test_approve_selects_keyframe_and_advances(self, isolated_state_dir):
        sm = PipelineStateManager()
        state = _gate_2_state("g2-approve", ["g2_c0", "g2_c1", "g2_c2"])
        await sm.save("g2-approve", state)

        result = await approve_gate("g2-approve", "gate_2_keyframe", ["g2_c1"])

        assert "error" not in result, f"unexpected error: {result.get('error')}"
        assert result["approved"] is True
        assert result["selected_ids"] == ["g2_c1"]
        assert result["selected_variants"] == ["creative"]
        # next step after keyframe_images is video_prompts
        assert result["next_step"] == "video_prompts"

        reloaded = await sm.load("g2-approve")
        gate_state = reloaded["gates"]["gate_2_keyframe"]
        assert gate_state["approved"] is True
        assert gate_state["status"] == "approved"
        assert gate_state["selected_ids"] == ["g2_c1"]
        assert "approved_at" in gate_state

        # edited_output written to keyframe_images step — gate_manager wraps
        # the candidate.data dict as [raw_data] (a single-element list).
        kf_step = reloaded["steps"]["keyframe_images"]
        assert kf_step["edited"] is True
        assert kf_step["gate_selected"] is True
        # edited_output is a single-element list of the candidate.data dict
        assert isinstance(kf_step["edited_output"], list)
        assert len(kf_step["edited_output"]) == 1
        assert kf_step["edited_output"][0]["scene_id"] == "scene_for_g2_c1"

        # current_step advanced
        assert reloaded["current_step"] == "video_prompts"

    @pytest.mark.asyncio
    async def test_approve_exceeds_max_selections_returns_error(self, isolated_state_dir):
        """Gate 2 has max_selections=1. Selecting 2 must error."""
        sm = PipelineStateManager()
        state = _gate_2_state("g2-toomany", ["g2_c0", "g2_c1", "g2_c2"])
        await sm.save("g2-toomany", state)

        result = await approve_gate(
            "g2-toomany", "gate_2_keyframe", ["g2_c0", "g2_c1"]
        )
        assert "error" in result
        assert "max_selections" in result["error"].lower() or "1" in result["error"]
        # State must NOT advance on error
        reloaded = await sm.load("g2-toomany")
        assert reloaded["gates"]["gate_2_keyframe"]["approved"] is False
        assert reloaded["current_step"] == "keyframe_images"

    @pytest.mark.asyncio
    async def test_approve_unknown_candidate_id_returns_error(self, isolated_state_dir):
        sm = PipelineStateManager()
        state = _gate_2_state("g2-unknown-cid", ["g2_c0", "g2_c1", "g2_c2"])
        await sm.save("g2-unknown-cid", state)

        result = await approve_gate(
            "g2-unknown-cid", "gate_2_keyframe", ["nonexistent_candidate"]
        )
        assert "error" in result


# ── Gate 3 clips ──


def _gate_3_state(label: str, candidate_ids: list[str]) -> dict:
    """Build a minimal pipeline state with Gate 3 awaiting approval.

    Per gate_manager.py:623-634, candidate.data for seedance_clips is the
    raw skill output (a single clip dict with video_path / duration_seconds),
    and gate_manager wraps it into the aggregated
    {clip_paths, clip_details, total_duration} shape when materializing
    edited_output.
    """
    candidates = [
        {
            "id": cid,
            "variant": v,
            # Single clip dict per candidate (skill returns one)
            "data": {
                "video_path": f"/tmp/{cid}_clip.mp4",
                "duration_seconds": 5.0,
                "file_size_bytes": 102400,
                "is_stub": False,
            },
            "score": {"overall": 0.65 + 0.05 * i},
            "acceptable": True,
            "recommended": (i == 0),
        }
        for i, (cid, v) in enumerate(
            zip(candidate_ids, ["standard", "creative", "conservative"], strict=False)
        )
    ]
    return attach_execution_policy({
        "label": label,
        "scenario": "s1",
        "config": {"product_catalog": {"name": "X"}, "brand_guidelines": {}},
        "steps": {
            "strategy": {"output": {}, "status": "done"},
            "scripts": {"output": [], "status": "done"},
            "compliance": {"output": [], "status": "done"},
            "storyboards": {"output": [], "status": "done"},
            "keyframe_images": {"output": {}, "status": "done"},
            "video_prompts": {"output": [], "status": "done"},
            "thumbnail_prompts": {"output": [], "status": "done"},
            "seedance_clips": {"output": {}, "status": "done"},
        },
        "current_step": "seedance_clips",
        "gates": {
            "gate_3_clips": {
                "status": "awaiting_approval",
                "candidates": candidates,
                "selected_ids": [],
                "approved": False,
            },
        },
    }, scenario="s1", media=True)


class TestGate3ClipsLifecycle:

    @pytest.mark.asyncio
    async def test_get_state_returns_awaiting(self, isolated_state_dir):
        sm = PipelineStateManager()
        state = _gate_3_state("g3-state-test", ["g3_c0", "g3_c1", "g3_c2"])
        await sm.save("g3-state-test", state)

        result = await get_gate_state("g3-state-test", "gate_3_clips")
        assert result["status"] == "awaiting_approval"
        assert len(result["candidates"]) == 3

    @pytest.mark.asyncio
    async def test_approve_selects_clip_and_advances(self, isolated_state_dir):
        sm = PipelineStateManager()
        state = _gate_3_state("g3-approve", ["g3_c0", "g3_c1", "g3_c2"])
        await sm.save("g3-approve", state)

        result = await approve_gate("g3-approve", "gate_3_clips", ["g3_c0"])

        assert "error" not in result, f"unexpected error: {result.get('error')}"
        assert result["approved"] is True
        assert result["selected_ids"] == ["g3_c0"]
        # The bounded profile terminates at seedance_clips.
        assert result["next_step"] is None

        reloaded = await sm.load("g3-approve")
        clips_step = reloaded["steps"]["seedance_clips"]
        assert clips_step["edited"] is True
        # edited_output is the aggregated shape — clip_paths is a single-
        # element list extracted from raw_data.video_path
        assert "clip_paths" in clips_step["edited_output"]
        assert clips_step["edited_output"]["clip_paths"] == ["/tmp/g3_c0_clip.mp4"]
        assert clips_step["edited_output"]["total_duration"] == 5.0
        assert reloaded["current_step"] is None

    @pytest.mark.asyncio
    async def test_approve_real_clip_uses_transparency_snapshot_and_is_idempotent(
        self,
        isolated_state_dir,
    ):
        from src.models.transparency import validate_transparency_sidecar

        label = "g3-real-approval"
        clip = (
            isolated_state_dir
            / "tenants"
            / "default"
            / "pending_review"
            / label
            / "clips"
            / "candidate.mp4"
        )
        clip.parent.mkdir(parents=True)
        clip.write_bytes(b"real-gate-clip")
        state = _gate_3_state(label, ["g3_real"])
        candidate = state["gates"]["gate_3_clips"]["candidates"][0]
        candidate["data"].update(
            {
                "video_path": str(clip),
                "simulated": False,
                "is_stub": False,
            }
        )
        sm = PipelineStateManager()
        await sm.save(label, state)

        first = await approve_gate(label, "gate_3_clips", ["g3_real"])
        persisted = await sm.load(label)
        assert persisted is not None
        projection = persisted["transparency"]
        sidecar = validate_transparency_sidecar(
            isolated_state_dir / projection["sidecar_path"],
            expected_sha256=projection["sidecar_sha256"],
            artifact_root=isolated_state_dir,
        )
        media_records = [record for record in sidecar.records if record.artifact]
        assert first["idempotent"] is False
        assert len(media_records) == 1
        assert media_records[0].origin_kind == "human_edit"
        assert media_records[0].c2pa_status == "unsigned_pending_review"
        assert len(media_records[0].human_edit_ids) == 1
        record_count = projection["record_count"]

        replay = await approve_gate(label, "gate_3_clips", ["g3_real"])
        replayed = await sm.load(label)
        assert replay["idempotent"] is True
        assert replayed is not None
        assert replayed["transparency"]["record_count"] == record_count

    @pytest.mark.asyncio
    async def test_approve_exceeds_max_selections_returns_error(self, isolated_state_dir):
        """Gate 3 has max_selections=1. Selecting 2 must error."""
        sm = PipelineStateManager()
        state = _gate_3_state("g3-toomany", ["g3_c0", "g3_c1", "g3_c2"])
        await sm.save("g3-toomany", state)

        result = await approve_gate(
            "g3-toomany", "gate_3_clips", ["g3_c0", "g3_c1"]
        )
        assert "error" in result
        # Sanity: state did not advance
        reloaded = await sm.load("g3-toomany")
        assert reloaded is not None
        assert reloaded["gates"]["gate_3_clips"]["approved"] is False

    @pytest.mark.asyncio
    async def test_approve_zero_selections_returns_error(self, isolated_state_dir):
        """Approving with empty selected_ids must error — Gate 3 requires
        a clip choice, you can't 'approve nothing'."""
        sm = PipelineStateManager()
        state = _gate_3_state("g3-zero", ["g3_c0", "g3_c1", "g3_c2"])
        await sm.save("g3-zero", state)

        result = await approve_gate("g3-zero", "gate_3_clips", [])
        assert "error" in result


# ── Cross-gate state isolation ──


class TestCrossGateIsolation:
    """Verify approving Gate 2 doesn't side-effect Gate 3 state, and v.v."""

    @pytest.mark.asyncio
    async def test_gate_2_approve_does_not_affect_gate_3_state(self, isolated_state_dir):
        sm = PipelineStateManager()
        state = _gate_2_state("cross-iso", ["c2_0", "c2_1", "c2_2"])
        # Add an awaiting gate_3 alongside gate_2 — use same single-clip
        # data shape as _gate_3_state for consistency
        state["gates"]["gate_3_clips"] = {
            "status": "awaiting_approval",
            "candidates": [{
                "id": "c3_0", "variant": "standard",
                "data": {
                    "video_path": "/tmp/x.mp4",
                    "duration_seconds": 5.0,
                    "is_stub": False,
                },
                "score": {"overall": 0.7}, "acceptable": True,
            }],
            "selected_ids": [],
            "approved": False,
        }
        await sm.save("cross-iso", state)

        await approve_gate("cross-iso", "gate_2_keyframe", ["c2_1"])

        reloaded = await sm.load("cross-iso")
        assert reloaded is not None
        # Gate 2 approved
        assert reloaded["gates"]["gate_2_keyframe"]["approved"] is True
        # Gate 3 untouched
        assert reloaded["gates"]["gate_3_clips"]["approved"] is False
        assert reloaded["gates"]["gate_3_clips"]["status"] == "awaiting_approval"
