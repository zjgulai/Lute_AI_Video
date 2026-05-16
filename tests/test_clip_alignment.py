"""CLIP alignment shim tests (D15).

Without loading the actual 600MB model, verify:
  - ClipAligner instantiation does not eagerly download model
  - score() returns None when not loaded
  - audit() returns "unknown" reason when CLIP unavailable
"""

from __future__ import annotations

from unittest.mock import patch

from src.quality.clip_alignment import ClipAligner


def test_clip_aligner_init_does_not_load_model():
    aligner = ClipAligner()
    assert aligner._model is None
    assert aligner._processor is None
    assert aligner._available is None


def test_clip_aligner_score_returns_none_when_unavailable():
    aligner = ClipAligner()
    with patch.object(aligner, "_load", return_value=False):
        result = aligner.score("/nonexistent/img.png", "a happy person")
    assert result is None


def test_clip_aligner_check_batch_reports_unavailable_when_clip_missing():
    aligner = ClipAligner()
    with patch.object(aligner, "_load", return_value=False):
        results = aligner.check_batch([("/nonexistent/img.png", "a happy person")])
    assert len(results) == 1
    r = results[0]
    assert r["score"] is None
    assert r["aligned"] is None
    assert "CLIP unavailable" in r["reason"]


def test_clip_aligner_load_caches_result():
    aligner = ClipAligner()
    aligner._available = False
    assert aligner._load() is False
    aligner._available = True
    assert aligner._load() is True
