"""Operational DeepSeek guidance must point at real, bounded controls."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "deepseek-timeout.md"


def test_429_guidance_is_time_bounded_and_names_the_real_pipeline_gate() -> None:
    text = RUNBOOK.read_text()

    assert "docker logs --since 1m" in text
    assert "OPT-E_SEEDANCE_SEMAPHORE" not in text
    assert "_pipeline_semaphore" not in text
    assert "runtime submit pause/concurrency control" in text
    assert "当前没有运行时暂停开关" in text
    assert "best-effort" in text
    assert "0 不能排除 429" in text
    assert "deploy maintenance" in text
    assert "不要" in text and "重启" in text
