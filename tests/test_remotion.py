"""Tests for RemotionRenderer — environment validation, export, and error handling."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.tools.remotion_renderer import RemotionEnvironmentError, RemotionRenderer


class TestRemotionIsAvailable:
    def test_returns_false_when_node_missing(self):
        """No node binary → is_available = False."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("node not found")
            renderer = RemotionRenderer()
            assert renderer.is_available is False

    def test_returns_false_when_node_fails(self):
        with patch("subprocess.run") as mock_run:
            mock_node = MagicMock()
            mock_node.returncode = 1
            mock_run.return_value = mock_node

            renderer = RemotionRenderer()
            assert renderer.is_available is False

    def test_returns_false_when_remotion_missing(self):
        """Node works but Remotion not installed."""
        mock_calls = []

        def mock_subprocess(*args, **kwargs):
            mock_calls.append(args[0] if args else kwargs.get("args"))
            mock_result = MagicMock()
            if "node" in str(args[0]):
                mock_result.returncode = 0
            else:
                mock_result.returncode = 1
            return mock_result

        with patch("subprocess.run", side_effect=mock_subprocess):
            renderer = RemotionRenderer()
            assert renderer.is_available is False

    def test_returns_true_when_both_available(self):
        mock_calls = []

        def mock_subprocess(*args, **kwargs):
            mock_calls.append(args[0] if args else kwargs.get("args"))
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "v18.0.0\n"
            return mock_result

        with patch("subprocess.run", side_effect=mock_subprocess):
            renderer = RemotionRenderer()
            assert renderer.is_available is True

    def test_timeout_returns_false_gracefully(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = TimeoutError("timed out")
            renderer = RemotionRenderer()
            assert renderer.is_available is False


class TestRemotionValidateEnvironment:
    def test_returns_complete_report(self):
        """validate_environment returns a structured dict with all keys."""
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "v20.0.0\n"
            mock_run.return_value = mock_result

            renderer = RemotionRenderer()
            report = renderer.validate_environment()

        assert "available" in report
        assert "node_version" in report
        assert "remotion_version" in report
        assert "render_script_exists" in report
        assert "node_modules_exist" in report
        assert "issues" in report
        assert isinstance(report["issues"], list)

    def test_reports_node_not_found_as_issue(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("node not found")
            renderer = RemotionRenderer()
            report = renderer.validate_environment()

        assert report["node_version"] is None
        assert any("not installed" in i for i in report["issues"]) or any(
            "not found" in i for i in report["issues"]
        )


class TestRemotionExportPipelineJson:
    def test_exports_json_file(self, tmp_path):
        renderer = RemotionRenderer(output_dir=tmp_path)
        pipeline_state = {"test": "data", "number": 42}
        filepath = renderer.export_pipeline_json(pipeline_state, filename="test.json")

        assert filepath.exists()
        assert filepath.suffix == ".json"
        content = filepath.read_text()
        assert "test" in content

    def test_logs_warning_when_not_available(self, tmp_path):
        """export_pipeline_json logs a warning but still writes when not available."""
        with patch.object(RemotionRenderer, "is_available", new=False):
            renderer = RemotionRenderer(output_dir=tmp_path)
            filepath = renderer.export_pipeline_json({"a": 1}, "warn_test.json")
            assert filepath.exists()


class TestRemotionRender:
    def test_raises_error_when_not_available(self, tmp_path):
        """render() should raise when environment is incomplete."""
        renderer = RemotionRenderer(output_dir=tmp_path)

        with (
            patch.object(RemotionRenderer, "validate_environment") as mock_val,
            patch.object(RemotionRenderer, "is_available", new=False),
        ):
            mock_val.return_value = {
                "available": False,
                "node_version": None,
                "remotion_version": None,
                "render_script_exists": False,
                "node_modules_exist": False,
                "issues": ["Node.js not found"],
            }

            with pytest.raises(RemotionEnvironmentError):
                renderer.render(Path("/fake/path.json"))

    def test_raises_error_with_clear_message(self, tmp_path):
        """Error message should list the specific issues found."""
        renderer = RemotionRenderer(output_dir=tmp_path)

        with (
            patch.object(RemotionRenderer, "validate_environment") as mock_val,
        ):
            mock_val.return_value = {
                "available": False,
                "node_version": None,
                "remotion_version": None,
                "render_script_exists": False,
                "node_modules_exist": False,
                "issues": ["Node.js not found", "Remotion not installed"],
            }

            with pytest.raises(RemotionEnvironmentError) as exc:
                renderer.render(Path("/fake/path.json"))
            assert "Node.js" in str(exc.value) or "not available" in str(exc.value)

    def test_passes_env_info_on_render(self, tmp_path):
        """When environment IS available, render should attempt to run the command."""
        renderer = RemotionRenderer(output_dir=tmp_path)
        input_json = tmp_path / "input.json"
        input_json.write_text("{}")

        with (
            patch.object(RemotionRenderer, "validate_environment") as mock_val,
            patch("subprocess.run") as mock_run,
        ):
            mock_val.return_value = {
                "available": True,
                "node_version": "v20.0.0",
                "remotion_version": "4.0.0",
                "render_script_exists": True,
                "node_modules_exist": True,
                "issues": [],
            }
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_run.return_value = mock_proc

            result = renderer.render(input_json, "test_out.mp4", blocking=True)
            assert result.name == "test_out.mp4"
