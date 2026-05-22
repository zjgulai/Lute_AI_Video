"""Helpers for normalizing media artifact outputs across pipeline scenarios."""

from __future__ import annotations

from typing import Any


def extract_assemble_paths(output: Any) -> tuple[str, str]:
    """Return ``(video_path, render_json_path)`` from assemble step output."""
    if isinstance(output, dict):
        return (
            str(output.get("video_path") or ""),
            str(output.get("render_json_path") or ""),
        )
    if isinstance(output, (list, tuple)):
        video_path = str(output[0] or "") if len(output) > 0 else ""
        render_json_path = str(output[1] or "") if len(output) > 1 else ""
        return video_path, render_json_path
    return "", ""
