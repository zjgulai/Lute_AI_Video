"""Script writer skill — generates video scripts from content briefs.

Uses LLM to produce structured 30-second short video scripts with
hook/solution/CTA segments. Falls back to template-generated scripts
when the LLM is unavailable.
"""

from __future__ import annotations

from typing import Any

import structlog

from src.config import DEFAULT_LANGUAGES
from src.skills.base import SkillCallable, SkillResult
from src.skills.registry import SkillRegistry

logger = structlog.get_logger()

import re

# Characters allowed in LLM prompt-injected strings (alphanumeric, Chinese, spaces, basic punctuation)
_PROMPT_SAFE_PATTERN = re.compile(r"[a-zA-Z0-9一-鿿぀-ゟ가-힯 ,.!?'\-+&/()@#:;《》【】…、—・%×]+")

def _sanitize_prompt_value(value: str, max_len: int = 200) -> str:
    """Strip dangerous characters and truncate for LLM prompt injection safety."""
    if not isinstance(value, str):
        return str(value)[:max_len]
    # Remove curly braces to prevent format() injection and LLM prompt manipulation
    cleaned = value.replace("{", "(").replace("}", ")").replace("\n", " ").replace("\r", "")
    # Keep only safe characters
    safe = "".join(ch for ch in cleaned if _PROMPT_SAFE_PATTERN.match(ch))
    return safe[:max_len].strip()

# ── System Prompts ──────────────────────────────────────────────────────

SCRIPT_WRITER_SYSTEM_PROMPT_EN = """You are an expert short-video script writer specializing in high-conversion content for brands.

## Your Task
Based on the product information and brand guidelines, generate a structured 30-second short video script.
Output MUST be strict JSON only — no markdown code blocks, no wrapping, no explanations.

## Script Structure (3 segments, strict 30 seconds)

### Hook — 0~3 seconds
- Grab attention within 3 seconds: pain-point reverse-question, data shock, contrast opening, or scene immersion
- MUST incorporate the P0 USP (highest priority selling point)
- Visual description must be impactful

### Body — 3~25 seconds
- Amplify pain point → present solution → show real results
- Naturally weave in one USP per round, no keyword stuffing
- Use relatable scenes and concrete examples

### CTA — 25~30 seconds
- Clear next-step guidance with moderate urgency
- Maintain brand tone — no gimmicks

## Writing Rules
1. Natural spoken language: sound like a real person, not an ad copy
2. Pause marks: use … for a 0.5s pause, 【】 for emphasis
3. Visual-driven: every voiceover must have a matching visual_description
4. USP distribution: P0 USP in hook segment, P1 USP in body, P2 USP before CTA
5. Forbidden: no competitor bashing, no medical claims, no exaggerated results
6. Brand keywords flow naturally, no repetitive stacking

## Output JSON Structure (strict)
{
  "segments": [
    {
      "segment_type": "hook",
      "start_time": 0, "end_time": 3,
      "voiceover": "Natural speech text with …【pauses and emphasis】",
      "visual_description": "Concrete visual description",
      "text_overlay": "On-screen text 3-6 characters"
    },
    {
      "segment_type": "solution",
      "start_time": 3, "end_time": 25,
      "voiceover": "Pain point + solution detailed narration",
      "visual_description": "Detailed scene description",
      "text_overlay": "On-screen text 3-8 characters"
    },
    {
      "segment_type": "cta",
      "start_time": 25, "end_time": 30,
      "voiceover": "CTA copy",
      "visual_description": "CTA visual scene description",
      "text_overlay": "CTA text 4-8 characters"
    }
  ],
  "hashtags": ["#tag1", "#tag2", "#tag3"],
  "cta_text": "Plain text call to action",
  "total_duration": 30
}

Important: Return ONLY pure JSON, no ```json markers, no explanatory text."""

# Chinese system prompt kept for backward compatibility when is_zh is True
SCRIPT_WRITER_SYSTEM_PROMPT_ZH = """你是一位资深的短视频脚本创作专家，专门为品牌制作高转化率的短视频脚本。

## 你的任务
根据产品信息和品牌指南，生成一个结构化的30秒短视频脚本。
输出必须是严格的JSON格式，不能包含markdown代码块或任何包装。

## 脚本结构（3段式，严格30秒）

### 钩子 Hook — 0~3秒
- 3秒内抓住注意力：痛点反问、数据冲击、反差开场或场景带入
- 必须融入P0 USP（最高优先级卖点）
- 视觉描述要有画面冲击力

### 主体 Body — 3~25秒
- 痛点放大 → 解决方案呈现 → 真实效果展示
- 每一轮自然地融入1个USP，禁止堆砌关键词
- 使用生活化场景和具体案例

### 行动号召 CTA — 25~30秒
- 明确的下一步指引，制造适度的紧迫感
- 保持品牌调性一致，不低俗

## 写作规则
1. 自然口语化：像真人说话，不是广告文案
2. 停顿标记：使用…表示0.5秒停顿，【】强调重音词
3. 视觉驱动：每个voiceover必须有匹配的visual_description
4. USP分布：P0 USP在钩子段，P1 USP在主体段，P2 USP在CTA前
5. 禁止：不攻击竞品、不作医疗声明、不夸大效果
6. 品牌关键词自然融入，不重复堆砌

## 输出JSON结构（严格）
{
  "segments": [
    {
      "segment_type": "hook",
      "start_time": 0, "end_time": 3,
      "voiceover": "口语化语音文本，带…【停顿和强调】",
      "visual_description": "具体的画面描述",
      "text_overlay": "画面叠加文字3-6字"
    },
    {
      "segment_type": "solution",
      "start_time": 3, "end_time": 25,
      "voiceover": "痛点+解决方案的详细叙述",
      "visual_description": "详细的画面描述",
      "text_overlay": "画面叠加文字3-8字"
    },
    {
      "segment_type": "cta",
      "start_time": 25, "end_time": 30,
      "voiceover": "行动号召文本",
      "visual_description": "CTA视觉画面描述",
      "text_overlay": "CTA文字4-8字"
    }
  ],
  "hashtags": ["#标签1", "#标签2", "#标签3"],
  "cta_text": "纯文本行动号召",
  "total_duration": 30
}

重要：只返回纯JSON，不要```json标记，不要任何解释文字。"""

SCRIPT_WRITER_USER_TEMPLATE = """Generate a 30-second short video script.

## Brief Info
Product: {product_name}
Brand: {brand_name}
USPs (prioritized): {usps}
Hook Type: {hook_type}
Video Type: {video_type}

## Brand Guidelines
{brand_guidelines}

## Platform: {platform}
## Language: {language}

Return ONLY valid JSON (no markdown wrapping, no explanations)."""

# ── Fallback Templates ───────────────────────────────────────────────────

FALLBACK_TEMPLATES = {
    "zh": {
        "hook_voiceover": "还在为{problem}烦恼吗？{product}给你全新答案…",
        "body_voiceover": "【{usp1}】是{product}的核心优势。配合{usp2}，让你的体验完全不一样。",
        "cta_voiceover": "点击下方链接，立即体验{product}！",
        "hook_visual": "痛点场景快速切换，【{product}】产品特写",
        "body_visual": "产品使用场景演示，{usp1}功能特写",
        "cta_visual": "品牌logo + 购买链接叠加",
    },
    "en": {
        "hook_voiceover": "Still struggling with {problem}? {product} has the solution…",
        "body_voiceover": "{product}'s 【{usp1}】and {usp2} make all the difference. See for yourself.",
        "cta_voiceover": "Click below to experience {product} today!",
        "hook_visual": "Problem scene → {product} reveal, dramatic lighting",
        "body_visual": "Product demo showcasing {usp1} in real use",
        "cta_visual": "Brand logo + purchase link overlay",
    },
}


class ScriptWriterSkill(SkillCallable):
    name = "script-writer-skill"
    description = "Generates structured video scripts from content briefs."

    def validate_params(self, params: dict) -> list[str]:
        errors = []
        if not params.get("briefs"):
            errors.append("'briefs' is required")
        return errors

    def validate_output(self, output: dict) -> list[str]:
        errors = []
        if not output:
            errors.append("output is None")
        return errors

    async def execute(self, params: dict) -> SkillResult:
        import asyncio
        from src.tools.llm_client import llm

        briefs = params["briefs"]
        languages = params.get("target_languages", DEFAULT_LANGUAGES)
        brand_guidelines = params.get("brand_guidelines", {})
        variant = params.get("variant", "standard")
        logger.info("script-writer: generating", count=len(briefs), langs=languages, variant=variant)

        # Parallel LLM calls: each brief × language combination runs concurrently
        async def _gen_one(brief: dict, lang: str) -> dict:
            try:
                script = await self._call_llm(brief, brand_guidelines, lang, llm, variant=variant)
                if script is None:
                    script = self._gen_fallback(brief, lang)
                return script
            except Exception:
                logger.warning("script-writer: LLM call failed, using fallback", brief_id=brief.get("id"), lang=lang)
                return self._gen_fallback(brief, lang)

        tasks = [_gen_one(brief, lang) for brief in briefs for lang in languages]
        scripts = await asyncio.gather(*tasks)

        return SkillResult(success=True, data={"scripts": list(scripts), "count": len(scripts)})

    async def _call_llm(
        self,
        brief: dict,
        brand_guidelines: dict,
        language: str,
        llm: Any,
        variant: str = "standard",
    ) -> dict | None:
        """Call the LLM to generate a script for one brief

        Accepts a variant parameter ("standard", "creative", "conservative") to
        adjust temperature and prompt tone for candidate generation.

        Returns a structured script dict on success, or None on failure.
        """
        import json

        # Temperature mapping for variant support
        VARIANT_TEMPERATURES = {
            "standard": 0.7,
            "creative": 0.9,
            "conservative": 0.5,
        }
        temperature = VARIANT_TEMPERATURES.get(variant, 0.7)

        # Variant-specific prompt suffix
        VARIANT_PROMPT_SUFFIXES = {
            "standard": "",
            "creative": "Be more creative and unexpected with hooks and storytelling angles.",
            "conservative": "Stay safe and conventional. Focus on clear product benefits. Avoid risky language.",
        }
        variant_suffix = VARIANT_PROMPT_SUFFIXES.get(variant, "")

        # Validate language code
        if not re.match(r'^[a-z]{2}(-[A-Z]{2})?$', language):
            language = "en"
        is_zh = language.startswith("zh")
        # Phase 2+3: primary prompt is English. Chinese prompt kept for backward compatibility.
        system_prompt = SCRIPT_WRITER_SYSTEM_PROMPT_ZH if is_zh else SCRIPT_WRITER_SYSTEM_PROMPT_EN

        # Append variant-specific prompt suffix if non-empty
        if variant_suffix:
            system_prompt = system_prompt + "\n\n" + variant_suffix

        product_name = _sanitize_prompt_value(brief.get("product_name", brief.get("topic", "Product")))
        raw_usps = brief.get("usp_priority", brief.get("usps", ["quality"]))
        usps = [_sanitize_prompt_value(u) for u in (raw_usps if isinstance(raw_usps, list) else [str(raw_usps)])]
        hook_type = _sanitize_prompt_value(brief.get("hook_type", "pain_point"))
        video_type = _sanitize_prompt_value(brief.get("video_type", "product_usage"))
        platform = (brief.get("target_platforms") or ["tiktok"])[0]

        user_message = SCRIPT_WRITER_USER_TEMPLATE.format(
            product_name=product_name,
            brand_name=_sanitize_prompt_value(brief.get("brand_name", "")),
            usps=json.dumps(usps, ensure_ascii=False),
            hook_type=hook_type,
            video_type=video_type,
            brand_guidelines=json.dumps(brand_guidelines, indent=2, ensure_ascii=False),
            platform=platform,
            language=language,
        )

        try:
            raw = await llm.invoke_json(system_prompt, user_message)
        except Exception:
            logger.warning("script-writer: LLM invoke failed", brief_id=brief.get("id"))
            return None
        if not isinstance(raw, dict):
            return None
        if "segments" not in raw or not isinstance(raw["segments"], list):
            return None

        segments = raw["segments"]
        for seg in segments:
            seg.setdefault("segment_type", seg.get("type", "unknown"))

        enriched = {
            "id": f"script-{brief.get('id', '?')}-{language}",
            "brief_id": brief.get("id", ""),
            "product_name": product_name,
            "brand_name": brief.get("brand_name", ""),
            "language": language,
            "platform": platform,
            "total_duration": raw.get("total_duration", 30),
            "segments": segments,
            "hashtags": raw.get("hashtags", []),
            "cta_text": raw.get("cta_text", ""),
            "hook_type": hook_type,
            "video_type": video_type,
        }
        return enriched

    def _gen_fallback(self, brief: dict, lang: str) -> dict:
        """Generate a structured script dict from template strings.

        Used when the LLM call fails or returns an invalid result.
        """
        pn = str(brief.get("product_name", brief.get("topic", "Product"))).replace("{", "(").replace("}", ")")
        usps = brief.get("usp_priority", brief.get("usps", ["quality"]))[:3]
        brand_name = brief.get("brand_name", "")
        hook_type = brief.get("hook_type", "pain_point")
        video_type = brief.get("video_type", "product_usage")
        platform = (brief.get("target_platforms") or ["tiktok"])[0]

        problem = str(brief.get("problem", "your daily challenges")).replace("{", "(").replace("}", ")")
        usp1 = str(usps[0] if len(usps) > 0 else "top feature").replace("{", "(").replace("}", ")")
        usp2 = str(usps[1] if len(usps) > 1 else "great value").replace("{", "(").replace("}", ")")

        key = "zh" if lang.startswith("zh") else "en"
        tpl = FALLBACK_TEMPLATES.get(key, FALLBACK_TEMPLATES["en"])

        segments = [
            {
                "segment_type": "hook",
                "start_time": 0,
                "end_time": 3,
                "voiceover": tpl["hook_voiceover"].format(problem=problem, product=pn),
                "visual_description": tpl["hook_visual"].format(problem=problem, product=pn),
                "text_overlay": pn[:6],
            },
            {
                "segment_type": "solution",
                "start_time": 3,
                "end_time": 25,
                "voiceover": tpl["body_voiceover"].format(usp1=usp1, usp2=usp2, product=pn),
                "visual_description": tpl["body_visual"].format(usp1=usp1, product=pn),
                "text_overlay": f"{usp1} + {usp2}"[:8],
            },
            {
                "segment_type": "cta",
                "start_time": 25,
                "end_time": 30,
                "voiceover": tpl["cta_voiceover"].format(product=pn),
                "visual_description": tpl["cta_visual"].format(product=pn),
                "text_overlay": "立即购买" if key == "zh" else "Shop Now",
            },
        ]

        return {
            "id": f"script-{brief.get('id', '?')}-{lang}",
            "brief_id": brief.get("id", ""),
            "product_name": pn,
            "brand_name": brand_name,
            "language": lang,
            "platform": platform,
            "total_duration": 30,
            "segments": segments,
            "hashtags": [f"#{pn.replace(' ', '')}"] if key == "en" else [f"#{pn}"],
            "cta_text": tpl["cta_voiceover"].format(product=pn),
            "hook_type": hook_type,
            "video_type": video_type,
        }

    def fallback(self, params: dict) -> SkillResult:
        briefs = params.get("briefs", [{"id": "fb", "topic": "Product"}])
        languages = params.get("target_languages", DEFAULT_LANGUAGES)
        scripts = []
        for brief in briefs[:2]:
            for lang in languages[:1]:
                scripts.append(self._gen_fallback(brief, lang))
        return SkillResult(success=True, data={"scripts": scripts, "count": len(scripts)})


try:
    SkillRegistry().register(ScriptWriterSkill())
    logger.info("skill registered", name=ScriptWriterSkill.name)
except ValueError:
    logger.info("skill already registered", name=ScriptWriterSkill.name)
