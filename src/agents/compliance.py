"""Compliance Agent — dual-layer content safety checker.

Layer 1: YAML rule engine (fast, deterministic, catches known patterns)
Layer 2: LLM review (semantic understanding, catches novel violations)

Phase 1 MVP: Rule engine active, LLM review as optional second pass.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import structlog
import yaml

from src.models import (
    AuditCriterionStatus,
    AuditReport,
    ComplianceFlag,
    ComplianceReport,
    ComplianceStatus,
    Script,
    Severity,
)
from src.tools.llm_client import llm

logger = structlog.get_logger()

RULES_PATH = Path(__file__).parent.parent / "data" / "compliance_rules.yaml"


def load_rules() -> list[dict[str, Any]]:
    with open(RULES_PATH) as f:
        data = yaml.safe_load(f)
    return data.get("rules", [])


def _find_precheck_criterion(report: AuditReport):
    """Extract status of the 'Compliance Pre-check' criterion from an AuditReport.

    Returns the AuditCriterionStatus (PASS/WARN/FAIL) of criterion #7,
    or None if the report doesn't contain one.
    """
    for c in report.criteria:
        if c.name == "Compliance Pre-check":
            return c.status
    return None


COMPLIANCE_SYSTEM_PROMPT = """You are a content compliance auditor for a baby-feeding e-commerce brand. 
Your job is to review video scripts for violations of platform policies (TikTok, Facebook, YouTube, Shopify)
and brand safety guidelines.

## What to Flag
1. Medical claims (cures, treats, prevents — without clinical evidence citation)
2. Body exposure / nudity descriptions (any nipple/breast references)
3. Unsubstantiated competitor comparisons
4. Fear-based or guilt-based marketing
5. Children appearing in commercial content
6. Platform-specific policy violations

## Output Format
For each script, return:
```json
{
  "script_id": "SCRIPT-001",
  "status": "PASS" | "FLAGGED" | "BLOCKED",
  "flags": [
    {
      "severity": "HIGH" | "MEDIUM" | "LOW",
      "line_index": 0,
      "text": "the problematic text",
      "issue": "description of the violation",
      "suggestion": "how to rewrite safely"
    }
  ]
}
```

BLOCKED = critical violation, cannot publish without complete rewrite
FLAGGED = moderate concern, should be reviewed but can proceed
PASS = no issues found
"""


class ComplianceAgent:
    """Dual-layer compliance checker for video scripts.

    Accepts an optional audit_report (AuditReport from script_audit_node)
    to short-circuit when the pre-check already determined all scripts are clean.
    The pre-check criterion #7 ('Compliance Pre-check') scores each script's
    red-flag count — if every script passed that check, there's no need to
    run the full rule engine again.
    """

    def __init__(self, use_mock: bool = False):
        self.rules = load_rules()
        self.use_mock = use_mock
        logger.info("compliance_agent: loaded rules", rule_count=len(self.rules))

    async def run(
        self,
        scripts: list[Script],
        script_audit_report: AuditReport | None = None,
    ) -> list[ComplianceReport]:
        # -- Short-circuit: if script audit pre-check already cleared everything --
        if script_audit_report is not None:
            pre_check = _find_precheck_criterion(script_audit_report)
            if pre_check is not None and pre_check == AuditCriterionStatus.PASS:
                logger.info(
                    "compliance: skipped full scan — script audit pre-check already PASS",
                    audit_id=script_audit_report.audit_id,
                )
                return [
                    ComplianceReport(script_id=s.id, status=ComplianceStatus.PASS)
                    for s in scripts
                ]

        reports = []
        for script in scripts:
            # Layer 1: Rule engine
            rule_flags = self._rule_check(script)

            # Determine status based on rule engine alone
            if any(f.severity == Severity.HIGH for f in rule_flags):
                status = ComplianceStatus.BLOCKED
            elif rule_flags:
                status = ComplianceStatus.FLAGGED
            else:
                status = ComplianceStatus.PASS

            report = ComplianceReport(
                script_id=script.id,
                status=status,
                flags=rule_flags,
            )
            reports.append(report)

            logger.info(
                "compliance: script checked",
                script_id=script.id,
                status=status.value,
                flag_count=len(rule_flags),
            )

        return reports

    def _rule_check(self, script: Script) -> list[ComplianceFlag]:
        """Layer 1: Fast regex-based rule engine."""
        flags = []
        # Concatenate all voiceover text with line indices
        lines = [seg.voiceover for seg in script.segments]

        for line_idx, text in enumerate(lines):
            for rule in self.rules:
                # Check platform applicability
                rule_platforms = rule.get("platforms", [])
                if rule_platforms and script.platform.value not in rule_platforms:
                    continue

                pattern = rule["pattern"]
                if re.search(pattern, text, re.IGNORECASE):
                    flags.append(
                        ComplianceFlag(
                            severity=Severity(rule["severity"]),
                            line_index=line_idx,
                            text=text[:200],
                            issue=rule["issue"],
                            suggestion=rule.get("suggestion", ""),
                        )
                    )

        return flags


async def llm_compliance_review(scripts: list[Script]) -> list[dict]:
    """Layer 2: LLM semantic review (optional, cost-aware)."""
    import json

    scripts_json = json.dumps(
        [s.model_dump(mode="json") for s in scripts], indent=2, default=str
    )
    try:
        result = await llm.invoke_json(
            COMPLIANCE_SYSTEM_PROMPT,
            f"Review these scripts for compliance issues:\n{scripts_json}",
        )
        return result if isinstance(result, list) else [result]
    except Exception as e:
        logger.error("compliance: LLM review failed", error=str(e))
        return []
