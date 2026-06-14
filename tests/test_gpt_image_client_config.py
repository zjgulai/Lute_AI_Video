from __future__ import annotations


def test_poyo_image_max_polls_is_runtime_configurable(monkeypatch) -> None:
    from src.tools.gpt_image_client import _poyo_image_max_polls

    monkeypatch.setenv("POYO_IMAGE_MAX_POLLS", "90")

    assert _poyo_image_max_polls() == 90


def test_poyo_image_max_polls_keeps_safe_default(monkeypatch) -> None:
    from src.tools.gpt_image_client import _poyo_image_max_polls

    monkeypatch.delenv("POYO_IMAGE_MAX_POLLS", raising=False)

    assert _poyo_image_max_polls() >= 60
