"""Medical / health-claim lexicon for maternal & baby product content moderation.

Sprint 3 P3-2 — closes diagnostic R-S1-COMP / R-S2-COMP / R-S3-COMP.

This module provides a curated list of forbidden medical/health claim phrases
in the maternal & infant care category. Phrases are sourced from FDA's
Forbidden Health Claims guidance, FTC's deceptive-advertising precedents, and
WHO misinformation framework. The list is **deliberately conservative**:
each phrase, when matched, indicates a script that would likely be rejected
by Meta / TikTok / YouTube ad review or trigger platform removal.

Phrases are grouped by **severity tier**:
- BANNED_CLAIMS: hard fail. Any match → script BLOCKED (do not proceed to
  generation). Includes disease-treatment claims and unproven cures.
- FLAGGED_CLAIMS: soft warning. Triggers a flag in compliance report but
  does not block; human reviewer should evaluate context (e.g., "supports
  immunity" may be permissible if backed by NDI/FDA citation).
- COMPETITOR_CLAIMS: comparative-superiority phrases that require legal
  substantiation (e.g., "best on the market" without citation).

Usage:
    from src.tools.medical_lexicon import (
        MEDICAL_BANNED_CLAIMS, MEDICAL_FLAGGED_CLAIMS,
        merge_medical_lexicon,
    )

    guidelines_with_lexicon = merge_medical_lexicon(brand_guidelines)
    # forbidden_content now includes all BANNED_CLAIMS

Layered defense:
- Layer 1 (this module): regex-free substring matching, <5ms latency.
- Layer 2 (Sprint 4+): SaaS API fallback (Hive/Sightengine) for novel
  claims not in the lexicon. NOT in scope for Sprint 3.

Maintenance: when production logs show platform rejections containing
phrases not in the lexicon, add them to the appropriate tier here.
"""

from __future__ import annotations

from typing import Any

# ── BANNED (hard fail): disease-treatment claims, unproven cures ──
# These are FDA structure/function violations or unapproved drug claims.
MEDICAL_BANNED_CLAIMS: list[str] = [
    # Disease names — claiming product treats/prevents a disease without FDA approval
    "cures cancer", "treats cancer", "prevents cancer", "shrinks tumor",
    "cures diabetes", "treats diabetes", "reverses diabetes",
    "cures autism", "reverses autism", "treats autism",
    "cures colic", "ends colic", "stops colic permanently",
    "cures eczema", "heals eczema permanently", "cures baby acne",
    "cures asthma", "treats asthma in infants", "prevents asthma",
    "cures allergies", "eliminates allergies", "treats food allergies",
    "treats reflux", "cures gerd", "cures acid reflux",
    "treats jaundice", "cures newborn jaundice",
    "treats sids", "prevents sids", "eliminates sids risk",
    "cures thrush", "treats oral thrush",
    "cures mastitis", "treats mastitis",
    "treats covid", "prevents covid", "cures covid-19",
    "cures rsv", "prevents rsv", "treats rsv",
    "cures ear infection", "treats otitis",
    # Drug-equivalent claims (FDA: any product claiming to act as a drug needs approval)
    "fda approved drug", "doctor prescribed", "medical grade treatment",
    "clinically proven cure", "scientifically proven cure",
    "guaranteed weight loss", "guaranteed results",
    "miracle cure", "natural cure",
    "kills bacteria 100%", "100% effective against virus",
    "antibiotic alternative", "replaces medication",
    # Infant safety violations (cannot promise life-safety outcomes)
    "prevents infant death", "guaranteed safe for sleep",
    "prevents sudden death", "eliminates choking risk",
    "100% bpa free guaranteed safe",
    # Direct medical advice
    "do not consult a doctor", "skip the pediatrician",
    "replaces medical advice", "replaces pediatric care",
    "as good as breastmilk", "better than breastmilk",
    "replaces breastfeeding", "complete breastmilk substitute",
    # Vaccine misinformation
    "alternative to vaccines", "replaces vaccines",
    "natural immunity instead of vaccine",
    # Detox / pseudoscience
    "detoxifies baby", "removes toxins from infant",
    "alkaline baby formula", "ph balanced cure",
    # Permanent / lifetime guarantees
    "permanent cure", "lifetime treatment", "never gets sick again",
    "guaranteed never ill",
]

# ── FLAGGED (soft warning): require substantiation but not auto-block ──
# These are structure/function claims that MAY be permissible with proper
# disclaimers or citations. Compliance reviewer must evaluate context.
MEDICAL_FLAGGED_CLAIMS: list[str] = [
    "boosts immunity", "boosts immune system", "strengthens immunity",
    "improves immunity", "supports immune function",
    "promotes brain development", "boosts iq", "improves cognitive development",
    "enhances brain function", "increases intelligence",
    "improves digestion", "aids digestion", "promotes gut health",
    "reduces gas", "eliminates gas",
    "promotes weight gain", "helps baby gain weight",
    "encourages healthy weight",
    "improves sleep", "helps baby sleep through night",
    "guarantees better sleep", "deeper sleep",
    "reduces crying", "stops crying instantly",
    "calms fussy baby", "soothes immediately",
    "improves bone development", "stronger bones",
    "promotes growth", "accelerates development",
    "enhances milestones", "speeds developmental milestones",
    "improves eyesight", "supports vision development",
    "improves hearing", "supports auditory development",
    "natural", "all-natural",  # bare "natural" without context is FTC-flagged
    "chemical-free",  # technically impossible — everything is chemicals
    "non-toxic",  # requires substantiation
    "organic",  # unless USDA-certified, this is regulated
    "hypoallergenic",  # FDA: not a defined term
    "doctor recommended",  # requires named doctor + disclosure
    "pediatrician recommended",  # same
    "lab tested",  # which lab? what test?
    "scientifically formulated",  # vague
    "clinically tested",  # FTC: requires citing the trial
    "dermatologist tested",  # ambiguous outcome
]

# ── COMPETITOR / SUPERIORITY CLAIMS ──
# Comparative claims require substantiation (FTC Section 5).
MEDICAL_COMPETITOR_CLAIMS: list[str] = [
    "best on the market", "#1 baby brand", "number one",
    "leading brand", "world's best",
    "outperforms all competitors", "better than all others",
    "voted best", "award winning",  # without source citation
    "trusted by all moms", "preferred by every mother",
    "endorsed by all pediatricians",
    "guaranteed to outperform",
]


# ── CHINESE / 简体 (产品多模态平台需要) ──
# 中文医疗禁用词，平行 BANNED + FLAGGED + COMPETITOR 层级。
# 来源：中国《广告法》第十七条 (禁止医疗用语) + 国家市场监督管理总局
# "广告内容关键词监管指引" + 国家药监局婴幼儿食品标识规范。
MEDICAL_BANNED_CLAIMS_ZH: list[str] = [
    "治疗癌症", "预防癌症", "治愈癌症", "消除肿瘤",
    "治疗糖尿病", "预防糖尿病", "逆转糖尿病",
    "治疗自闭症", "治愈自闭症",
    "治疗肠绞痛", "永久止住肠绞痛",
    "治疗湿疹", "根治湿疹", "治愈宝宝湿疹",
    "治疗哮喘", "预防婴儿哮喘",
    "治疗过敏", "根治过敏", "消除过敏",
    "治疗胃食管反流", "治愈反流",
    "治疗黄疸", "治愈新生儿黄疸",
    "预防婴儿猝死综合征", "消除猝死风险",
    "治疗鹅口疮",
    "治疗乳腺炎",
    "预防新冠", "治疗新冠",
    "替代药物", "免吃药", "代替吃药",
    "不用看医生", "替代儿科治疗",
    "比母乳更好", "完全替代母乳",
    "替代疫苗", "代替疫苗",
    "排毒", "净化宝宝身体", "去除婴儿毒素",
    "永久治愈", "终身免疫",
    "百分百安全", "100% 防止意外",
    "保证不生病", "保证孩子健康",
    "保证有效", "保证瘦身",
    "神奇配方", "灵丹妙药",
    "医院专用", "医生处方",
    "药品级别", "临床验证治愈",
]

MEDICAL_FLAGGED_CLAIMS_ZH: list[str] = [
    "增强免疫力", "提高免疫力", "改善免疫",
    "促进大脑发育", "提升智商", "增强认知",
    "改善消化", "促进消化", "舒缓肠胃",
    "促进体重增长", "帮助宝宝长胖",
    "改善睡眠", "助眠", "深度睡眠",
    "减少哭闹", "停止哭闹", "瞬间安抚",
    "增强骨骼", "促进骨骼发育",
    "加速发育", "促进发育", "缩短发育时间",
    "改善视力", "保护视力发育",
    "改善听力",
    "天然无添加", "纯天然",
    "无化学成分",
    "无毒",
    "有机",
    "低敏",
    "医生推荐", "儿科医生推荐",
    "实验室检测", "科学配方",
    "临床测试",
    "皮肤科医生测试",
]

MEDICAL_COMPETITOR_CLAIMS_ZH: list[str] = [
    "市场第一", "行业第一", "全网第一",
    "领先品牌", "世界最好",
    "超越所有竞品", "比所有其他都好",
    "获奖产品", "评为最佳",
    "所有妈妈信赖", "每个母亲首选",
    "所有医生背书",
]


def get_all_medical_terms() -> list[str]:
    """Return concatenation of EN+ZH × (BANNED + FLAGGED + COMPETITOR) lists.

    Use this when wiring into BrandComplianceSkill's `forbidden_content`,
    which treats every entry as a single severity tier. For multi-tier
    enforcement, call ``merge_medical_lexicon`` which preserves severity.
    """
    return [
        *MEDICAL_BANNED_CLAIMS,
        *MEDICAL_FLAGGED_CLAIMS,
        *MEDICAL_COMPETITOR_CLAIMS,
        *MEDICAL_BANNED_CLAIMS_ZH,
        *MEDICAL_FLAGGED_CLAIMS_ZH,
        *MEDICAL_COMPETITOR_CLAIMS_ZH,
    ]


# Phase 0 #3 (2026-05-15): severity-aware classification map. Closes the
# Oracle-identified regression where BrandCompliance was collapsing all 3
# tiers (BANNED / FLAGGED / COMPETITOR) into severity="high", causing
# benign phrases like "natural lighting" or "doctor recommended" to be
# treated as hard-blocks instead of warnings.
#
# Severity contract:
# - "high"  → BLOCKED (script must not generate)
# - "low"   → FLAGGED (warning surfaced to reviewer, generation continues)
#
# Lookups use case-insensitive substring match identical to BrandCompliance,
# so terms map back to their tier even when matched as part of a larger
# phrase.


def get_term_severity(term: str) -> str:
    """Return "high" if `term` is in any BANNED tier, else "low".

    Returns "high" by default for unknown terms — preserves backward-compat
    with callers that supplied custom forbidden_content entries expecting
    high-severity (the pre-Phase-0 behavior).
    """
    t = term.lower().strip()
    banned_set = {*[s.lower() for s in MEDICAL_BANNED_CLAIMS],
                  *[s.lower() for s in MEDICAL_BANNED_CLAIMS_ZH]}
    flagged_set = {*[s.lower() for s in MEDICAL_FLAGGED_CLAIMS],
                   *[s.lower() for s in MEDICAL_FLAGGED_CLAIMS_ZH],
                   *[s.lower() for s in MEDICAL_COMPETITOR_CLAIMS],
                   *[s.lower() for s in MEDICAL_COMPETITOR_CLAIMS_ZH]}
    if t in banned_set:
        return "high"
    if t in flagged_set:
        return "low"
    return "high"


def build_severity_map() -> dict[str, str]:
    """Return a {term: "high"|"low"} dict for every term in the lexicon.

    BrandComplianceSkill caches this once and looks up matched terms in O(1).
    Caller-provided forbidden_content entries that are NOT in this map default
    to "high" (backward-compat).
    """
    out: dict[str, str] = {}
    for term in (*MEDICAL_BANNED_CLAIMS, *MEDICAL_BANNED_CLAIMS_ZH):
        out[term.lower()] = "high"
    for term in (
        *MEDICAL_FLAGGED_CLAIMS,
        *MEDICAL_FLAGGED_CLAIMS_ZH,
        *MEDICAL_COMPETITOR_CLAIMS,
        *MEDICAL_COMPETITOR_CLAIMS_ZH,
    ):
        out[term.lower()] = "low"
    return out


def merge_medical_lexicon(
    brand_guidelines: dict[str, Any] | None,
    *,
    include_flagged: bool = True,
    include_competitor: bool = True,
    include_chinese: bool = True,
) -> dict[str, Any]:
    """Return a copy of `brand_guidelines` with the medical lexicon merged into
    `forbidden_content` so BrandComplianceSkill auto-detects medical claims.

    Phase 0 #3 (2026-05-15): also writes ``_medical_lexicon_severity`` —
    a {term_lower: "high"|"low"} dict that BrandComplianceSkill reads to
    avoid collapsing FLAGGED + COMPETITOR tiers into BLOCKED. Caller-
    provided forbidden_content entries default to "high" (back-compat).

    Args:
        brand_guidelines: existing dict or None; None returns dict with just
            the medical lexicon.
        include_flagged: when True (default), include FLAGGED claims (soft
            warnings). Set False to only block hard violations.
        include_competitor: when True (default), include COMPETITOR claims.
        include_chinese: when True (default), include 中文 tiers (for content
            targeted at CN-language platforms / Douyin / Xiaohongshu).

    Returns:
        dict with merged `forbidden_content` (BANNED + optional tiers +
        any caller-provided entries, deduplicated) and
        ``_medical_lexicon_severity`` map.
    """
    base: list[str] = list(MEDICAL_BANNED_CLAIMS)
    if include_flagged:
        base.extend(MEDICAL_FLAGGED_CLAIMS)
    if include_competitor:
        base.extend(MEDICAL_COMPETITOR_CLAIMS)
    if include_chinese:
        base.extend(MEDICAL_BANNED_CLAIMS_ZH)
        if include_flagged:
            base.extend(MEDICAL_FLAGGED_CLAIMS_ZH)
        if include_competitor:
            base.extend(MEDICAL_COMPETITOR_CLAIMS_ZH)

    result = dict(brand_guidelines) if brand_guidelines else {}
    existing = list(result.get("forbidden_content", []) or [])
    # Preserve caller-provided entries first so brand-specific overrides win.
    combined = existing + [term for term in base if term not in existing]
    result["forbidden_content"] = combined
    result["_medical_lexicon_severity"] = build_severity_map()
    return result
