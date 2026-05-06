"""Internationalization service — English-only (v0.x).

v0.x 仅支持英语输出。多语言架构已简化,未来扩展时在此文件恢复。
"""

from __future__ import annotations

from typing import Any


# English is the only supported language in v0.x.
_SUPPORTED_LANGS: dict[str, str] = {"en": "English"}


def _normalize_lang(lang: str) -> str:
    """Normalize language code. v0.x always returns 'en'."""
    return "en"


class I18nService:
    """Resolves prompts and templates — English only."""

    @staticmethod
    def supported_languages() -> dict[str, str]:
        return dict(_SUPPORTED_LANGS)

    @staticmethod
    def get_prompt(agent_name: str, lang: str) -> Any:
        """Always return the English prompt module."""
        import importlib
        return importlib.import_module(f"src.agents.prompts.{agent_name}_en")

    @staticmethod
    def get_translated_templates(lang: str) -> None:
        """English uses built-in templates directly."""
        return None

    @staticmethod
    def get_translated_prompt_text(lang: str) -> None:
        """English uses built-in prompt directly."""
        return None
