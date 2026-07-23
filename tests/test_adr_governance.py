"""Architecture decision records remain immutable and use successors."""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
ADR_DIR = REPO_ROOT / "docs" / "architecture" / "adr"


def test_adr_006_keeps_original_decision_and_is_superseded_by_008() -> None:
    original = (ADR_DIR / "006-c2pa-content-credentials.md").read_text()
    successor = (ADR_DIR / "008-transparency-evidence-boundary.md").read_text()
    index = (ADR_DIR / "README.md").read_text()

    assert "Accepted Option A: CA-issued publisher cert + c2pa-python in backend image" in original
    assert "## 2026-07-23 clarification" not in original
    assert "Superseded by ADR-008" in original
    assert "supersedes ADR-006" in successor
    assert "signed_local_readback" in successor
    assert "不得把本地" in successor
    assert "[008](./008-transparency-evidence-boundary.md)" in index
    assert "006" in index and "Superseded by 008" in index


def test_adr_008_has_complete_governed_frontmatter() -> None:
    text = (ADR_DIR / "008-transparency-evidence-boundary.md").read_text()
    assert text.startswith("---\n")
    _, raw_frontmatter, _ = text.split("---", 2)
    frontmatter = yaml.safe_load(raw_frontmatter)

    assert frontmatter["doc_type"] == "architecture"
    assert frontmatter["status"] == "stable"
    assert frontmatter["created"].isoformat() == "2026-07-23"
    assert frontmatter["updated"].isoformat() == "2026-07-23"
    assert frontmatter["owner"]
    assert frontmatter["source"] == "human+ai"
    assert any(
        item["file"] == "./006-c2pa-content-credentials.md"
        and item["relation"] == "supersedes"
        for item in frontmatter["related"]
    )
