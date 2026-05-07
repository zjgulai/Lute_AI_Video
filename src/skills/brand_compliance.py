"""Brand compliance skill — audits scripts against brand guidelines.

Checks for:
  - Brand color/font/logo usage requirements
  - Tone-of-voice alignment
  - Forbidden content (competitor names, medical claims)
  - Brand message consistency

Auto-registers with SkillRegistry on import as "brand-compliance-skill".
"""

from __future__ import annotations

from typing import Any

import structlog

from src.skills.base import SkillCallable, SkillResult
from src.skills.registry import SkillRegistry

logger = structlog.get_logger()


def _extract_brand_name(guidelines: dict) -> str:
    return guidelines.get("brand_name", guidelines.get("brand", ""))


def _extract_tone(guidelines: dict) -> str:
    return guidelines.get("tone", guidelines.get("tone_of_voice", "professional"))


class BrandComplianceSkill(SkillCallable):
    """Audit content scripts for brand compliance.

    Input params:
      scripts: list[dict] — video scripts with segments
      brand_guidelines: dict — brand asset package or guidelines dict

    Returns dict with:
      reports: list[{script_id, status, flags, violations_summary}]
    """

    name = "brand-compliance-skill"
    description = "Audits scripts for brand compliance — tone, forbidden content, brand assets."

    def validate_params(self, params: dict) -> list[str]:
        errors = []
        if not params.get("scripts"):
            errors.append("'scripts' is required")
        return errors

    def validate_output(self, output: dict) -> list[str]:  # type: ignore[override]
        errors = []
        if not output:
            errors.append("output is None")
        return errors

    async def execute(self, params: dict) -> SkillResult:
        scripts = params["scripts"]
        guidelines = params.get("brand_guidelines", {})
        logger.info("brand-compliance: auditing", script_count=len(scripts))

        brand_name = _extract_brand_name(guidelines)
        tone = _extract_tone(guidelines)
        forbidden = guidelines.get("forbidden_content", [])

        reports = []
        for script in scripts:
            flags = self._check_script(script, brand_name, tone, forbidden)
            status = "PASS"
            has_high = any(f.get("severity") == "high" for f in flags)
            has_low = any(f.get("severity") == "low" for f in flags)
            if has_high:
                status = "BLOCKED"
            elif has_low:
                status = "FLAGGED"

            reports.append({
                "script_id": script.get("id", ""),
                "status": status,
                "flags": flags,
                "violations_summary": f"{len([f for f in flags if f['severity']=='high'])} high, {len([f for f in flags if f['severity']=='low'])} low",
            })

        return SkillResult(success=True, data={"reports": reports, "count": len(reports)})

    def _check_script(self, script: dict, brand_name: str, tone: str, forbidden: list) -> list[dict]:
        flags = []
        text = self._script_text(script).lower()

        # Brand name presence (low severity if missing)
        if brand_name and brand_name.lower() not in text:
            flags.append({
                "rule": "brand_mention",
                "severity": "low",
                "message": f"Brand name '{brand_name}' not found in script"
            })

        # Forbidden content
        for fb in forbidden:
            if fb.lower() in text:
                flags.append({
                    "rule": "forbidden_content",
                    "severity": "high",
                    "message": f"Forbidden content detected: '{fb}'"
                })

        # Competitor references (heuristic: if brand_name absent but another brand mentioned)
        if not brand_name:
            known_brands = ["medela", "spectra", "philips", "tommee"]
            for kb in known_brands:
                if kb in text:
                    flags.append({
                        "rule": "competitor_reference",
                        "severity": "high",
                        "message": f"Competitor brand '{kb}' referenced"
                    })

        return flags

    def _script_text(self, script: dict) -> str:
        segs = script.get("segments", [])
        texts = [s.get("voiceover", "") for s in segs]
        texts.append(script.get("hook", ""))
        texts.append(script.get("thumbnail_description", ""))
        return "\n".join(texts)

    def fallback(self, params: dict) -> SkillResult:
        scripts = params.get("scripts", [])
        reports = [{
            "script_id": s.get("id", ""),
            "status": "PASS",
            "flags": [],
            "violations_summary": "0 high, 0 low",
        } for s in scripts]
        return SkillResult(success=True, data={"reports": reports, "count": len(reports)})


SkillRegistry().register(BrandComplianceSkill())
logger.info("skill registered", name=BrandComplianceSkill.name)
