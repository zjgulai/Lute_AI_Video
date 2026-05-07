"""Regression tests for portfolio mechanism.

Coverage:
- portfolio_index scanner generates valid index against a synthetic output/ tree
- WebhookManager.subscribe + dispatch fires in-process listeners
- portfolio_hook auto-registers on pipeline.completed and runs rebuild
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from typing import Any


# ── Scanner: synthetic output/ tree ──


def test_portfolio_index_scans_synthetic_tree(tmp_path, monkeypatch):
    """Scanner walks output/, classifies by subdir, fills scenario/label when matched."""
    import scripts.portfolio_index as pi

    # Lay down a fake output/ structure
    output = tmp_path / "output"
    (output / "renders").mkdir(parents=True)
    (output / "seedance").mkdir(parents=True)
    (output / "gpt_images").mkdir(parents=True)
    (output / "audio").mkdir(parents=True)
    (output / "pipeline_states").mkdir(parents=True)

    # File matching ^s\d_\d+ → scenario / label populated, linked_state populated
    rendered = output / "renders" / "s1_1700000000.mp4"
    rendered.write_bytes(b"fake mp4")
    state_file = output / "pipeline_states" / "s1_1700000000.json"
    state_file.write_text("{}")

    # File NOT matching pattern → scenario / label null
    (output / "seedance" / "seedance_ABC123_xyz.mp4").write_bytes(b"fake")
    (output / "gpt_images" / "poyo_img_random.png").write_bytes(b"fake")
    (output / "audio" / "cosyvoice_en_abc.mp3").write_bytes(b"fake")
    # Non-media file should be skipped
    (output / "renders" / "s1_1700000000_input.json").write_text("{}")

    # Point scanner at the synthetic tree
    portfolio_dir = tmp_path / "assets" / "portfolio"
    monkeypatch.setattr(pi, "OUTPUT_DIR", output)
    monkeypatch.setattr(pi, "PIPELINE_STATES_DIR", output / "pipeline_states")
    monkeypatch.setattr(pi, "PORTFOLIO_DIR", portfolio_dir)
    monkeypatch.setattr(pi, "INDEX_PATH", portfolio_dir / "index.json")
    monkeypatch.setattr(pi, "PROJECT_ROOT", tmp_path)

    index = pi.rebuild_index()

    assert index["schema_version"] == "1.0"
    assert index["summary"]["total_files"] == 4  # excludes _input.json
    cats = index["summary"]["by_category"]
    assert cats["renders"]["count"] == 1
    assert cats["seedance"]["count"] == 1
    assert cats["gpt_images"]["count"] == 1
    assert cats["audio"]["count"] == 1

    # The s1_1700000000.mp4 should have label / linked_state populated
    rendered_entry = next(f for f in index["files"] if f["category"] == "renders")
    assert rendered_entry["scenario"] == "s1"
    assert rendered_entry["label"] == "s1_1700000000"
    assert rendered_entry["linked_state"] == "output/pipeline_states/s1_1700000000.json"
    assert rendered_entry["source"] == "remotion_assemble"

    # The seedance file lacks a scenario marker → null
    seedance_entry = next(f for f in index["files"] if f["category"] == "seedance")
    assert seedance_entry["scenario"] is None
    assert seedance_entry["label"] is None
    assert seedance_entry["linked_state"] is None
    assert seedance_entry["source"] == "seedance_video_generate"

    # Index file written + valid JSON
    written = json.loads((portfolio_dir / "index.json").read_text())
    assert written["summary"]["total_files"] == 4


# ── WebhookManager.subscribe + dispatch in-process ──


@pytest.mark.asyncio
async def test_subscribe_listener_fires_on_dispatch():
    from src.tools.webhook_manager import (
        EVENT_PIPELINE_COMPLETED,
        WebhookManager,
    )

    wm = WebhookManager()
    received: list[dict[str, Any]] = []

    def sync_listener(payload):
        received.append({"sync": True, "payload": payload})

    async def async_listener(payload):
        received.append({"async": True, "payload": payload})

    wm.subscribe(EVENT_PIPELINE_COMPLETED, sync_listener)
    wm.subscribe(EVENT_PIPELINE_COMPLETED, async_listener)

    await wm.dispatch(EVENT_PIPELINE_COMPLETED, {"thread_id": "t1"})
    # Give async listener a tick to run (fire-and-forget)
    await asyncio.sleep(0.05)

    assert len(received) == 2
    assert any(r.get("sync") for r in received)
    assert any(r.get("async") for r in received)
    assert all(r["payload"]["thread_id"] == "t1" for r in received)


@pytest.mark.asyncio
async def test_subscribe_idempotent():
    from src.tools.webhook_manager import EVENT_PIPELINE_COMPLETED, WebhookManager

    wm = WebhookManager()

    def listener(payload):
        pass

    wm.subscribe(EVENT_PIPELINE_COMPLETED, listener)
    wm.subscribe(EVENT_PIPELINE_COMPLETED, listener)  # dup

    assert len(wm._listeners[EVENT_PIPELINE_COMPLETED]) == 1


@pytest.mark.asyncio
async def test_listener_exception_does_not_break_dispatch():
    from src.tools.webhook_manager import EVENT_PIPELINE_COMPLETED, WebhookManager

    wm = WebhookManager()
    second_called = []

    def bad_listener(payload):
        raise RuntimeError("boom")

    def good_listener(payload):
        second_called.append(payload)

    wm.subscribe(EVENT_PIPELINE_COMPLETED, bad_listener)
    wm.subscribe(EVENT_PIPELINE_COMPLETED, good_listener)

    # Dispatch should not raise; second listener should still run
    await wm.dispatch(EVENT_PIPELINE_COMPLETED, {"thread_id": "t2"})

    assert len(second_called) == 1


# ── Portfolio hook end-to-end ──


@pytest.mark.asyncio
async def test_portfolio_hook_registers_and_fires(tmp_path, monkeypatch):
    """register_portfolio_hook subscribes; pipeline.completed triggers rebuild."""
    import scripts.portfolio_index as pi
    from src.tools.webhook_manager import (
        EVENT_PIPELINE_COMPLETED,
        get_webhook_manager,
        reset_webhook_manager,
    )

    # Synthetic output/ for the rebuild to run against
    output = tmp_path / "output"
    (output / "renders").mkdir(parents=True)
    (output / "renders" / "s1_1700000000.mp4").write_bytes(b"fake")
    portfolio_dir = tmp_path / "assets" / "portfolio"

    monkeypatch.setattr(pi, "OUTPUT_DIR", output)
    monkeypatch.setattr(pi, "PIPELINE_STATES_DIR", output / "pipeline_states")
    monkeypatch.setattr(pi, "PORTFOLIO_DIR", portfolio_dir)
    monkeypatch.setattr(pi, "INDEX_PATH", portfolio_dir / "index.json")
    monkeypatch.setattr(pi, "PROJECT_ROOT", tmp_path)

    reset_webhook_manager()
    from src.tools.portfolio_hook import register_portfolio_hook
    register_portfolio_hook()

    wm = get_webhook_manager()
    await wm.dispatch(EVENT_PIPELINE_COMPLETED, {"thread_id": "t-hook"})
    # Threadpool + fire-and-forget — give it time to land
    for _ in range(20):
        if (portfolio_dir / "index.json").exists():
            break
        await asyncio.sleep(0.05)

    assert (portfolio_dir / "index.json").exists()
    written = json.loads((portfolio_dir / "index.json").read_text())
    assert written["summary"]["total_files"] == 1

    reset_webhook_manager()
