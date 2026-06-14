"""Guard the portfolio thumbnail coverage dry-run reporter."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "portfolio_thumbnail_coverage.py"
CONTRACT = REPO_ROOT / "configs" / "thumbnail-coverage-dry-run-contract.yaml"
RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "thumbnail-missing.md"


def _write_large_video(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"0" * (1024 * 1024 + 1))


def test_thumbnail_coverage_report_is_read_only(tmp_path, monkeypatch):
    import scripts.portfolio_thumbnail_coverage as coverage
    import src.tools.poster_extractor as poster_extractor

    output_dir = tmp_path / "output"
    _write_large_video(output_dir / "renders" / "s1_1700000000.mp4")
    _write_large_video(output_dir / "seedance" / "s1_1700000000_clip_1.mp4")
    (output_dir / "renders" / "tiny_stub.mp4").write_bytes(b"stub")
    (output_dir / "audio").mkdir(parents=True)
    (output_dir / "audio" / "voice.mp3").write_bytes(b"audio")
    _write_large_video(output_dir / "brand_assets" / "momcozy" / "sku" / "images" / "brand-video.mp4")

    poster = output_dir / "thumbnails" / "portfolio_posters" / "renders__s1_1700000000.jpg"
    poster.parent.mkdir(parents=True)
    poster.write_bytes(b"jpg")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("thumbnail coverage dry-run must not generate posters")

    monkeypatch.setattr(poster_extractor, "ensure_poster", fail_if_called)

    report = coverage.build_thumbnail_coverage_report(output_dir=output_dir)

    assert report["total_videos"] == 2
    assert report["with_thumbnail"] == 1
    assert report["missing_thumbnail"] == 1
    assert report["coverage_pct"] == 50.0
    assert report["by_kind"]["final_work"]["coverage_pct"] == 100.0
    assert report["by_kind"]["creation_intermediate"]["coverage_pct"] == 0.0
    assert report["missing"][0]["path"] == "seedance/s1_1700000000_clip_1.mp4"
    assert not (output_dir / "thumbnails" / "portfolio_posters" / "seedance__s1_1700000000_clip_1.jpg").exists()


def test_thumbnail_coverage_cli_outputs_json_without_mutating(tmp_path):
    output_dir = tmp_path / "output"
    _write_large_video(output_dir / "renders" / "s1_1700000000.mp4")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--output-dir", str(output_dir), "--format", "json"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["dry_run"] is True
    assert data["total_videos"] == 1
    assert data["missing_thumbnail"] == 1
    assert not (output_dir / "thumbnails" / "portfolio_posters").exists()


def test_thumbnail_coverage_contract_and_runbook_document_no_generation():
    assert CONTRACT.exists()
    contract = CONTRACT.read_text()
    runbook = RUNBOOK.read_text()

    for token in [
        "scripts/portfolio_thumbnail_coverage.py",
        "generate_missing=false",
        "no_generation: true",
        "scripts/generate_portfolio_thumbnails.py",
    ]:
        assert token in contract

    for token in [
        "scripts/portfolio_thumbnail_coverage.py",
        "DRY RUN",
        "不会生成 poster",
        "generate_missing=False",
        "scripts/generate_portfolio_thumbnails.py",
    ]:
        assert token in runbook
