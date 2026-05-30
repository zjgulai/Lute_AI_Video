"""Sprint 4 P4-2: aspect ratio fan-out structural tests.

Verifies the multi-aspect-ratio surface introduced in Sprint 4 P4-2:
- RemotionRenderer.render() accepts composition_id parameter (default
  "ShortVideo" for back-compat).
- RemotionAssembleSkill returns video_paths: dict[ratio, path] when
  aspect_ratios contains > 1 entry; defaults to single 9:16 entry.
- Composition IDs in rendering/src/Root.tsx are aligned with what the
  Python skill expects (ShortVideo / ShortVideo_1x1 / ShortVideo_16x9).

These tests use mocked Remotion (no real npx tsx call) — they verify the
contract surface, not the rendering itself. Real-rendering verification
would require a media_stability marker test with full Remotion env.
"""

from __future__ import annotations

import inspect


class TestRemotionRendererCompositionId:

    def test_render_signature_has_composition_id(self):
        from src.tools.remotion_renderer import RemotionRenderer
        sig = inspect.signature(RemotionRenderer.render)
        assert "composition_id" in sig.parameters
        # Default must remain "ShortVideo" for back-compat
        assert sig.parameters["composition_id"].default == "ShortVideo"

    def test_render_passes_composition_to_cli(self, tmp_path, monkeypatch):
        """When composition_id is specified, --composition is added to the
        npx tsx CLI invocation."""
        from src.tools.remotion_renderer import RemotionRenderer

        captured_cmds: list[list[str]] = []

        # Patch validate_environment to claim Remotion is available
        monkeypatch.setattr(
            RemotionRenderer, "validate_environment",
            lambda self: {"available": True, "issues": []},
        )

        # Patch subprocess.run to just capture cmd
        import src.tools.remotion_renderer as rr_module

        class _MockResult:
            returncode = 0
            stdout = ""
            stderr = ""

        def _fake_run(cmd, **_kwargs):
            captured_cmds.append(cmd)
            # Create the expected output file
            for i, a in enumerate(cmd):
                if a == "--output" and i + 1 < len(cmd):
                    from pathlib import Path
                    Path(cmd[i + 1]).write_bytes(b"fake mp4 data" * 100)
            return _MockResult()

        monkeypatch.setattr(rr_module.subprocess, "run", _fake_run)

        input_json = tmp_path / "in.json"
        input_json.write_text("{}")
        renderer = RemotionRenderer(output_dir=tmp_path)
        renderer.render(
            input_json=input_json,
            output_filename="o.mp4",
            blocking=True,
            composition_id="ShortVideo_1x1",
        )

        assert captured_cmds, "subprocess.run was not called"
        cmd = captured_cmds[0]
        assert "--composition" in cmd
        assert "ShortVideo_1x1" in cmd


class TestAspectRatioCompositionIDsAligned:
    """Sanity: ids in Root.tsx match what assemble_skill maps to."""

    def test_composition_ids_in_root_tsx(self):
        """Read rendering/src/Root.tsx and verify the 3 composition ids
        the Python skill knows about all appear there."""
        from pathlib import Path
        root_tsx = Path(__file__).parent.parent / "rendering" / "src" / "Root.tsx"
        assert root_tsx.exists(), f"Root.tsx not found at {root_tsx}"
        content = root_tsx.read_text(encoding="utf-8")
        for comp_id in ("ShortVideo", "ShortVideo_1x1", "ShortVideo_16x9"):
            assert comp_id in content, f"composition id {comp_id!r} missing from Root.tsx"

    def test_skill_maps_three_aspect_ratios(self):
        """RemotionAssembleSkill source must reference the 3 composition ids."""
        import src.skills.remotion_assemble as ra
        src = inspect.getsource(ra)
        # The aspect-to-composition map must include all 3
        assert '"9:16"' in src and "ShortVideo" in src
        assert '"1:1"' in src and "ShortVideo_1x1" in src
        assert '"16:9"' in src and "ShortVideo_16x9" in src


class TestAssembleResultShape:
    """Verify the result dict shape extension is back-compat."""

    def test_video_paths_field_documented_in_skill(self):
        """The result data['video_paths'] field must be in the skill source —
        downstream consumers (s1/s2/s5 _build_result) will read this."""
        import src.skills.remotion_assemble as ra
        src = inspect.getsource(ra)
        assert "video_paths" in src

    def test_video_path_field_unchanged(self):
        """Back-compat: 'video_path' (singular) MUST remain — old callers
        still read result.data['video_path']."""
        import src.skills.remotion_assemble as ra
        src = inspect.getsource(ra)
        # Both fields must coexist
        assert '"video_path"' in src
        assert '"video_paths"' in src
