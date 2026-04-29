"""Internationalization service — multi-language prompt + template resolution.

Provides:
- Language-specific prompt modules for Strategy and ScriptWriter agents
- Translated script templates for mock mode (ES/FR/DE, falling back to EN)
- Centralized language support registry

Usage:
    from src.agents.i18n import I18nService
    i18n = I18nService()
    templates = i18n.get_translated_templates("es")
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger()

# ── Supported languages ──

_SUPPORTED_LANGS: dict[str, str] = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
}


def _normalize_lang(lang: str) -> str:
    """Normalize language code (e.g. 'EN' -> 'en', 'es-ES' -> 'es')."""
    norm = lang.lower().split("-")[0].split("_")[0]
    if norm in _SUPPORTED_LANGS:
        return norm
    # Fallback to English for unsupported languages
    return "en"


# ── I18nService ──


class I18nService:
    """Resolves prompts and templates by language code.

    Service methods:
      - get_prompt(agent_name, lang) -> module with SYSTEM_PROMPT + TEMPLATE attrs
      - get_translated_templates(lang) -> dict of script templates in that language
      - supported_languages() -> dict[str, str]
    """

    @staticmethod
    def supported_languages() -> dict[str, str]:
        """Return {code: name} for all supported languages."""
        return dict(_SUPPORTED_LANGS)

    @staticmethod
    def get_prompt(agent_name: str, lang: str) -> Any:
        """Get the prompt module for a given agent and language.

        Args:
            agent_name: 'strategy' or 'script_writer'
            lang: language code (en/es/fr/de)

        Returns:
            A module-like object with SYSTEM_PROMPT and TEMPLATE attrs.
            Falls back to English if the language module doesn't exist.

        Raises:
            ValueError: if agent_name is unknown.
        """
        norm = _normalize_lang(lang)
        module_path = f"src.agents.prompts.{agent_name}_{norm}"

        # English is always the fallback
        if norm != "en":
            try:
                import importlib

                mod = importlib.import_module(module_path)
                logger.debug("i18n: loaded prompt module", module=module_path)
                return mod
            except (ImportError, ModuleNotFoundError):
                logger.warning(
                    "i18n: prompt not found, falling back to English",
                    lang=lang,
                    module=module_path,
                )

        # Fallback to English
        import importlib

        return importlib.import_module(f"src.agents.prompts.{agent_name}_en")

    @staticmethod
    def get_translated_templates(lang: str) -> dict[str, dict[str, str]] | None:
        """Get translated script templates for a language.

        Args:
            lang: target language code.

        Returns:
            Dict of {brief_id: template_dict} or None if no translations exist.
            English returns None (uses the built-in _SCRIPT_TEMPLATES).
        """
        norm = _normalize_lang(lang)
        if norm == "en":
            return None  # English uses the built-in templates directly

        try:
            import importlib

            mod = importlib.import_module(f"src.agents.prompts.script_writer_{norm}")
            templates_key = f"_SCRIPT_TEMPLATES_{norm.upper()}"
            templates = getattr(mod, templates_key, None)
            if templates is not None:
                logger.debug("i18n: loaded templates", lang=norm, count=len(templates))
                return templates
            logger.warning(
                "i18n: no templates in module",
                lang=norm,
            )
            return None
        except (ImportError, ModuleNotFoundError):
            logger.warning(
                "i18n: template module not found, falling back to English",
                lang=norm,
            )
            return None

    @staticmethod
    def get_translated_prompt_text(lang: str) -> str | None:
        """Get the translated user message template for script writer.

        Returns the template string for LLM mode, or None for English.
        """
        norm = _normalize_lang(lang)
        if norm == "en":
            return None

        try:
            import importlib

            mod = importlib.import_module(f"src.agents.prompts.script_writer_{norm}")
            template = getattr(mod, "SCRIPT_WRITER_USER_MESSAGE_TEMPLATE", None)
            return template
        except (ImportError, ModuleNotFoundError):
            return None
