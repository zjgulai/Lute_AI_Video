"""Chinese-to-English translation via LLM for product inputs.

Detects Chinese characters in input text and translates them to English
using the configured LLM client (Kimi/Moonshot). Handles errors gracefully
by returning the original text on failure.
"""

import re

import structlog
from src.tools.llm_client import llm

logger = structlog.get_logger()

# Unicode range for CJK Unified Ideographs (Chinese characters)
_CHINESE_PATTERN = re.compile(r'[一-鿯]')

# Safety limit: truncate input to this many characters before sending to LLM
_MAX_TRANSLATE_LENGTH = 8000


def has_chinese(text: str) -> bool:
    """Return True if the string contains any Chinese characters."""
    if not isinstance(text, str):
        return False
    return bool(_CHINESE_PATTERN.search(text))


async def translate_to_english(text: str) -> str:
    """Translate Chinese text to English via the configured LLM.

    If no Chinese characters are detected, returns the original text unchanged.
    If the LLM call fails for any reason, logs a warning and returns the
    original text so the pipeline can continue.

    Args:
        text: Input text that may contain Chinese.

    Returns:
        English translation on success, original text on failure or no-op.
    """
    if not isinstance(text, str) or not text.strip():
        return text

    if not has_chinese(text):
        return text

    # Truncate very long text to avoid LLM context window issues
    if len(text) > _MAX_TRANSLATE_LENGTH:
        text = text[:_MAX_TRANSLATE_LENGTH]
        logger.warning("translate: input truncated",
                       original_len=len(text), max_length=_MAX_TRANSLATE_LENGTH)

    system_prompt = (
        "You are a professional Chinese-to-English translator. "
        "Translate the user's text to English accurately. "
        "Return ONLY the English translation, with no explanation, no notes, no preamble."
    )
    user_message = f"Translate the following Chinese text to English. Return ONLY the English translation, no explanation.\n\n{text}"

    try:
        result = await llm.invoke(system_prompt=system_prompt, user_message=user_message)
        translated = result.strip()
        logger.info("translate: success", original_len=len(text), translated_len=len(translated))
        return translated
    except Exception:
        logger.warning("translate: LLM call failed, returning original text", text_preview=text[:80])
        return text


async def translate_catalog_to_english(catalog: dict) -> dict:
    """Translate a product_catalog dict's name and USPs to English.

    Returns a new dict with translated fields. The original Chinese values
    are preserved in ``_original_zh`` sub-fields so the UI can show them.

    Args:
        catalog: Product catalog dict with optional 'name' and 'usps' keys.

    Returns:
        Translated catalog dict with ``_original_zh`` metadata.
    """
    if not isinstance(catalog, dict):
        return catalog

    result = dict(catalog)
    original_zh: dict[str, str] = {}

    name = catalog.get("name", "")
    if name and has_chinese(name):
        original_zh["name"] = name
        result["name"] = await translate_to_english(name)

    usps = catalog.get("usps", [])
    if isinstance(usps, list):
        translated_usps: list[str] = []
        for usp in usps:
            if isinstance(usp, str) and has_chinese(usp):
                original_zh.setdefault("usps", [])
                original_zh["usps"].append(usp)  # type: ignore[union-attr]
                translated_usps.append(await translate_to_english(usp))
            else:
                translated_usps.append(usp)
        result["usps"] = translated_usps

    if original_zh:
        result["_original_zh"] = original_zh
        logger.info("translate_catalog: done", keys=list(original_zh.keys()))

    # Nested products[0] fields
    products = catalog.get("products", [])
    if products and isinstance(products, list) and len(products) > 0:
        p = dict(products[0])

        # String fields
        for field in ["name", "usage_scenario", "target_audience"]:
            val = p.get(field, "")
            if has_chinese(val):
                p[field] = await translate_to_english(val)

        # List-of-strings fields
        for field in ["pain_points", "competitor_context"]:
            vals = p.get(field, [])
            if isinstance(vals, list):
                p[field] = [
                    await translate_to_english(v) if has_chinese(str(v)) else v
                    for v in vals
                ]

        result["products"][0] = p

    return result
