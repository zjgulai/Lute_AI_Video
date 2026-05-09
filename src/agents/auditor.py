"""Self-audit agent — deterministic rule-based scoring before human review.

Each audit method is fast (<50ms) and reproducible — no LLM calls.
Scores are designed to produce realistic distributions:
  - Strategy audits: 0.80-0.95 (usually WARN, sometimes PASS)
  - Script audits: 0.70-0.90 (wider variance, more FAILs)
  - Edit audits: 0.75-0.95
  - Thumbnail audits: 0.70-0.95

Thresholds used by routing (in routing.py):
  - score > 0.90: auto-approve (skip human review)
  - score < 0.60: auto-reject (shut down pipeline)
  - 0.60-0.90: normal human review required
"""

from __future__ import annotations

import re
from typing import Any

from src.models import (
    AuditCheckpoint,
    AuditCriterion,
    AuditCriterionStatus,
    AuditReport,
    EditComposition,
    Script,
    ThumbnailSet,
    WeeklyCalendar,
)


def _score_to_status(score: float) -> AuditCriterionStatus:
    """Map a 0-1 score to PASS/WARN/FAIL status."""
    if score >= 0.80:
        return AuditCriterionStatus.PASS
    elif score >= 0.50:
        return AuditCriterionStatus.WARN
    return AuditCriterionStatus.FAIL


def _overall_status(criteria: list[AuditCriterion]) -> AuditCriterionStatus:
    """Aggregate per-criterion status: any FAIL → FAIL, any WARN → WARN, else PASS."""
    has_fail = any(c.status == AuditCriterionStatus.FAIL for c in criteria)
    has_warn = any(c.status == AuditCriterionStatus.WARN for c in criteria)
    if has_fail:
        return AuditCriterionStatus.FAIL
    if has_warn:
        return AuditCriterionStatus.WARN
    return AuditCriterionStatus.PASS


def _make_criterion(name: str, score: float, observation: str, recommendation: str = "") -> AuditCriterion:
    """Build a criterion with auto-classified status from a 0-1 score."""
    return AuditCriterion(
        name=name,
        status=_score_to_status(score),
        score=score,
        observation=observation,
        recommendation=recommendation,
    )


class AuditorAgent:
    """Self-audits pipeline artifacts before human review.

    Each audit is deterministic rule-based scoring — no LLM call.
    Future: optional LLM-powered semantic audit for nuanced checks.
    """

    # Segment type → emotional valence mapping for _score_emotional_arc
    _VALENCE_MAP: dict[str, str] = {
        "hook": "attention",
        "problem": "negative",
        "pain_point": "negative",
        "frustration": "negative",
        "agitation": "negative",
        "solution": "positive",
        "benefit": "positive",
        "proof": "positive",
        "trust_building": "positive",
        "social_proof": "positive",
        "testimonial": "positive",
        "usp": "positive",
        "guarantee": "positive",
        "authority": "positive",
        "scarcity": "urgent",
        "cta": "urgent",
        "urgency": "urgent",
        "final_hook": "urgent",
        "transition": "neutral",
    }

    # ═══ Async API (called by pipeline nodes) ═══

    async def run_strategy_audit(self, calendar, target_platforms, brand_guidelines=None):
        """Async wrapper called by strategy_audit_node."""
        return self.audit_strategy(calendar, target_platforms, brand_guidelines)

    async def run_script_audit(self, scripts, brand_guidelines=None):
        """Async wrapper called by script_audit_node."""
        return [self.audit_script(s, brand_guidelines) for s in scripts]

    async def run_edit_audit(self, compositions):
        """Async wrapper called by editing_audit_node."""
        return [self.audit_edit(c) for c in compositions]

    async def run_thumbnail_audit(self, thumbnail_sets, brand_guidelines=None):
        """Async wrapper called by thumbnail_audit_node."""
        return [self.audit_thumbnail(ts, brand_guidelines) for ts in thumbnail_sets]

    # ═══ Sync API (unit-tested directly) ═══

    def audit_strategy(
        self,
        calendar: WeeklyCalendar,
        target_platforms: list[str],
        brand_guidelines: dict[str, Any] | None = None,
    ) -> AuditReport:
        """Audit the weekly content calendar against 6 criteria."""
        briefs = calendar.briefs
        criteria: list[AuditCriterion] = []

        # 1. Platform Coverage
        platforms_in_briefs = set()
        for b in briefs:
            for p in b.target_platforms:
                platforms_in_briefs.add(p.value if hasattr(p, "value") else str(p))
        missing_targets = [p for p in target_platforms if p not in platforms_in_briefs]
        coverage = (
            1.0
            if not missing_targets
            else max(0.0, 1.0 - len(missing_targets) / len(target_platforms))
        )
        criteria.append(
            _make_criterion(
                "Platform Coverage",
                coverage,
                (
                    f"All {len(target_platforms)} target platforms covered"
                    if not missing_targets
                    else f"Missing platforms: {', '.join(missing_targets)}"
                ),
                "Ensure every target platform has at least 1 brief"
                if missing_targets
                else "",
            )
        )

        # 2. Type Diversity
        types_used = set()
        for b in briefs:
            vt = b.video_type.value if hasattr(b.video_type, "value") else str(b.video_type)
            types_used.add(vt)
        diversity_score = min(1.0, len(types_used) / 4.0)
        criteria.append(
            _make_criterion(
                "Type Diversity",
                diversity_score,
                f"{len(types_used)} video types used: {', '.join(sorted(types_used))}",
                "Mix at least 3 different video types across the week"
                if len(types_used) < 3
                else "",
            )
        )

        # 3. USP Mapping
        usps = brand_guidelines.get("usps", []) if brand_guidelines else []
        all_keywords: set[str] = set()
        for b in briefs:
            for usp in b.usp_priority:
                all_keywords.add(usp.lower())
        usp_score = 0.7
        if usps:
            covered = sum(1 for u in usps if any(u.lower() in kw for kw in all_keywords))
            usp_score = covered / len(usps) if usps else 0.7
        criteria.append(
            _make_criterion(
                "USP Mapping",
                usp_score,
                f"USP keywords appearing in briefs: {len(all_keywords)} unique terms",
            )
        )

        # 4. Audience Specificity
        audience_count = sum(1 for b in briefs if b.target_audience and b.target_audience.lower() != "everyone")
        audience_score = min(1.0, audience_count / max(1, len(briefs)))
        criteria.append(
            _make_criterion(
                "Audience Specificity",
                audience_score,
                f"{audience_count}/{len(briefs)} briefs have specific target audiences",
                "Replace 'everyone' with a specific audience segment" if audience_count < len(briefs) else "",
            )
        )

        # 5. Competitor / Trend Anchoring
        competitor_count = sum(1 for b in briefs if b.competitor_reference)
        competitor_score = min(1.0, competitor_count / max(1, len(briefs) // 2))
        criteria.append(
            _make_criterion(
                "Competitor / Trend Anchoring",
                competitor_score,
                f"{competitor_count}/{len(briefs)} briefs reference competitors or trends",
                "Anchor content against competitor weaknesses or trending topics"
                if competitor_count < 2
                else "",
            )
        )

        # 6. Seasonal Relevance
        seasonal_count = sum(1 for b in briefs if b.seasonal_hook)
        seasonal_score = min(1.0, seasonal_count / max(1, len(briefs) // 2))
        criteria.append(
            _make_criterion(
                "Seasonal Relevance",
                seasonal_score,
                f"{seasonal_count}/{len(briefs)} briefs have seasonal hooks",
                "Add seasonal hooks to at least half the briefs"
                if seasonal_count < len(briefs) // 2 + 1
                else "",
            )
        )

        overall_score = round(sum(c.score for c in criteria) / len(criteria), 2)
        return AuditReport(
            audit_id=f"AUDIT-STRATEGY-{hash(str(calendar.week)) & 0xFFFF:04x}",
            checkpoint=AuditCheckpoint.STRATEGY,
            target_artifact_id=str(calendar.week),
            overall_score=overall_score,
            overall_status=_overall_status(criteria),
            criteria=criteria,
            summary=f"Strategy audit: {overall_score:.0%} overall. "
                    f"{sum(1 for c in criteria if c.status == AuditCriterionStatus.FAIL)} fail, "
                    f"{sum(1 for c in criteria if c.status == AuditCriterionStatus.WARN)} warn, "
                    f"{sum(1 for c in criteria if c.status == AuditCriterionStatus.PASS)} pass.",
        )

    def audit_script(
        self,
        script: Script,
        brand_guidelines: dict[str, Any] | None = None,
    ) -> AuditReport:
        """Audit a single script against 7 criteria."""
        criteria: list[AuditCriterion] = []
        segments = script.segments

        # 1. Hook Strength (duration + text quality)
        hook_segments = [s for s in segments if s.segment_type == "hook"]
        hook_duration = 0.0
        hook_text = ""
        if hook_segments:
            longest_hook = max(hook_segments, key=lambda s: s.end_time - s.start_time)
            hook_duration = longest_hook.end_time - longest_hook.start_time
            hook_text = (longest_hook.voiceover or "").strip()
            # Duration sub-score: ≤3s = full points, ≤5s = partial, >5s = fail
            dur_score = 1.0 if hook_duration <= 3.0 else (0.5 if hook_duration <= 5.0 else 0.0)
        else:
            dur_score = 0.0

        # Text quality sub-score: curiosity gap + pattern interrupt
        text_score = self._score_hook_text(hook_text) if hook_text else 0.0

        # Combined: duration 40% weight, text quality 60% weight
        hook_score = dur_score * 0.4 + text_score * 0.6

        obs_parts: list[str] = []
        if hook_segments:
            obs_parts.append(f"duration {hook_duration:.1f}s")
        else:
            obs_parts.append("no hook segment")
        if hook_text:
            obs_parts.append(f"text: '{hook_text[:50]}...'" if len(hook_text) > 50 else f"text: '{hook_text}'")
        else:
            obs_parts.append("no hook text")

        rec = ""
        if not hook_segments:
            rec = "Add an attention-grabbing hook in the first 3 seconds"
        elif hook_duration > 3:
            rec = "Hook should be ≤ 3 seconds for short-form video"
        elif text_score < 0.6 and hook_text:
            rec = "Strengthen hook with curiosity gap (question/number/contrast) or pattern interrupt (stop/wait/mistake)"

        criteria.append(
            _make_criterion(
                "Hook Strength",
                hook_score,
                "; ".join(obs_parts),
                rec,
            )
        )

        # 2. Segment Completeness
        types_present = {s.segment_type for s in segments}
        required_types = {"hook", "pain_point", "solution", "trust_building", "cta"}
        missing = required_types - types_present
        completeness_score = 1.0 - len(missing) / len(required_types)
        criteria.append(
            _make_criterion(
                "Segment Completeness",
                completeness_score,
                f"Missing segments: {', '.join(sorted(missing))}" if missing else "All 5 segment types present",
                "Include all 5 segment types: hook, pain_point, solution, trust_building, cta"
                if missing
                else "",
            )
        )

        # 3. Duration Fit
        duration = script.total_duration
        if 20 <= duration <= 90:
            dur_score = 1.0
        elif 10 <= duration <= 180:
            dur_score = 0.5
        else:
            dur_score = 0.2
        criteria.append(
            _make_criterion(
                "Duration Fit",
                dur_score,
                f"Duration: {duration:.1f}s",
                "Target duration: 20-90s for short-form video"
                if not (20 <= duration <= 90)
                else "",
            )
        )

        # 4. Voiceover Clarity
        voiceovers = [s.voiceover for s in segments if s.voiceover]
        avg_words = 0.0
        if voiceovers:
            avg_words = sum(len(v.split()) for v in voiceovers) / len(voiceovers)
            voice_score = min(1.0, avg_words / 15.0)
        else:
            voice_score = 0.3
        criteria.append(
            _make_criterion(
                "Voiceover Clarity",
                voice_score,
                f"Average {avg_words:.0f} words per segment" if voiceovers else "No voiceover text",
                "Each segment should have at least 10 words of voiceover"
                if voiceovers and avg_words < 10
                else "Add voiceover text to all segments" if not voiceovers
                else "",
            )
        )

        # 5. Brand Voice
        tone = brand_guidelines.get("tone_of_voice", {}) if brand_guidelines else {}
        keywords = set(tone.get("keywords", []))
        voice_text = " ".join(s.voiceover for s in segments).lower()
        if keywords:
            matched = sum(1 for kw in keywords if kw.lower() in voice_text)
            brand_score = matched / len(keywords)
        else:
            brand_score = 0.7
        criteria.append(
            _make_criterion(
                "Brand Voice",
                brand_score,
                f"Matched {len(keywords) - sum(1 for kw in keywords if kw.lower() not in voice_text)}/{len(keywords)} brand keywords"
                if keywords
                else "No brand keywords to match against",
            )
        )

        # 6. CTA Clarity
        cta = script.cta_text
        cta_score = 1.0 if len(cta) > 20 else (0.5 if cta else 0.0)
        criteria.append(
            _make_criterion(
                "CTA Clarity",
                cta_score,
                f"CTA: '{cta[:60]}...'" if cta else "No CTA",
                "Add a clear call-to-action (20+ characters)" if not cta or len(cta) <= 20 else "",
            )
        )

        # 7. Compliance Pre-check
        all_text = " ".join(s.voiceover for s in segments).lower()
        banned_terms = ["guaranteed", "100%", "best in the world", "cure", "miracle", "instant"]
        found_terms = [t for t in banned_terms if t in all_text]
        precheck_score = 1.0 - (len(found_terms) * 0.2)
        criteria.append(
            _make_criterion(
                "Compliance Pre-check",
                precheck_score,
                f"Flagged terms: {', '.join(found_terms)}" if found_terms else "No compliance issues detected",
                "Remove or soften: guaranteed, 100%, cure — these trigger platform filters"
                if found_terms
                else "",
            )
        )

        # 8. Information Density (words-per-second)
        total_words = sum(len((s.voiceover or "").split()) for s in segments)
        total_duration = max(script.total_duration, 1.0)
        wps = total_words / total_duration
        # Target: 2.5-3.5 wps for short-form video
        if 2.5 <= wps <= 3.5:
            density_score = 1.0
            density_obs = f"Information density {wps:.1f} words/s — optimal for short-form"
            density_rec = ""
        elif 2.0 <= wps < 2.5 or 3.5 < wps <= 4.0:
            density_score = 0.7
            density_obs = f"Information density {wps:.1f} words/s — slightly off optimal (2.5-3.5)"
            density_rec = "Adjust script length or segment timing" if wps > 3.5 else "Add more detail or extend duration"
        elif 1.5 <= wps < 2.0 or 4.0 < wps <= 5.0:
            density_score = 0.4
            density_obs = f"Information density {wps:.1f} words/s — outside ideal range"
            density_rec = "Shorten script or increase duration" if wps > 4.0 else "Add more content or reduce duration"
        else:
            density_score = 0.1
            density_obs = f"Information density {wps:.1f} words/s — severely off"
            density_rec = "Significantly adjust script length or segment timing"
        criteria.append(
            _make_criterion(
                "Information Density",
                density_score,
                density_obs,
                density_rec,
            )
        )

        # 9. Emotional Arc — check negative→positive progression + urgency at CTA
        emotion_score = self._score_emotional_arc(segments)
        criteria.append(
            _make_criterion(
                "Emotional Arc",
                emotion_score["score"],
                emotion_score["observation"],
                emotion_score["recommendation"],
            )
        )

        # P1: New criteria (Information Density, Emotional Arc) are observation-only
        # for backward compatibility — included in criteria list for visibility,
        # but not in overall_score calculation until PR-2 calibration.
        _core_names = {
            "Hook Strength", "Segment Completeness", "Duration Fit",
            "Voiceover Clarity", "Brand Voice", "CTA Clarity", "Compliance Pre-check",
        }
        core_criteria = [c for c in criteria if c.name in _core_names]
        overall_score = round(sum(c.score for c in core_criteria) / len(core_criteria), 2) if core_criteria else 0.5
        return AuditReport(
            audit_id=f"AUDIT-SCRIPT-{script.id}",
            checkpoint=AuditCheckpoint.SCRIPT,
            target_artifact_id=script.id,
            overall_score=overall_score,
            overall_status=_overall_status(criteria),
            criteria=criteria,
            summary=f"Script '{script.id}' audit: {overall_score:.0%} overall.",
        )

    def audit_edit(
        self,
        composition: EditComposition,
    ) -> AuditReport:
        """Audit an edit composition against 6 criteria."""
        criteria: list[AuditCriterion] = []
        timeline = composition.timeline

        # 1. Shot Continuity
        gaps = 0
        for i in range(1, len(timeline)):
            prev_end = timeline[i - 1].end_time
            curr_start = timeline[i].start_time
            if abs(curr_start - prev_end) > 0.1:
                gaps += 1
        continuity_score = 1.0 - (gaps * 0.33)
        criteria.append(
            _make_criterion(
                "Shot Continuity",
                continuity_score,
                f"{gaps} timing gaps detected" if gaps else "No timing gaps",
                "Shots should have no gaps between end_time and next start_time"
                if gaps
                else "",
            )
        )

        # 2. Asset Coverage
        asset_count = len({e.asset_id for e in timeline})
        coverage_score = min(1.0, asset_count / 3.0)
        criteria.append(
            _make_criterion(
                "Asset Coverage",
                coverage_score,
                f"{asset_count} unique assets used across {len(timeline)} events",
                "Use at least 3 unique assets for visual variety"
                if asset_count < 3
                else "",
            )
        )

        # 3. Duration Accuracy
        dur_accuracy = 1.0 - abs(composition.total_duration - (max(e.end_time for e in timeline) if timeline else 0)) / max(composition.total_duration, 1.0)
        criteria.append(
            _make_criterion(
                "Duration Accuracy",
                min(1.0, dur_accuracy),
                f"Total: {composition.total_duration}s, Timeline: {max(e.end_time for e in timeline):.1f}s" if timeline else "Empty timeline",
            )
        )

        # 4. Transition Quality
        transitions = {e.transition for e in timeline}
        variety_score = min(1.0, len(transitions) / 3.0)
        if len(timeline) > 0 and all(t == "cut" for t in transitions):
            variety_score = 0.4
        criteria.append(
            _make_criterion(
                "Transition Quality",
                variety_score,
                f"Transitions: {', '.join(sorted(transitions))}",
                "Mix at least 2 different transition types (cut, dissolve, zoom, slide)"
                if len(transitions) < 2
                else "",
            )
        )

        # 5. Aspect Ratio
        ar = composition.aspect_ratio
        aspect_score = 1.0 if ar == "9:16" else 0.0
        criteria.append(
            _make_criterion(
                "Aspect Ratio",
                aspect_score,
                f"Aspect ratio: {ar}",
                "Use 9:16 for short-form video (TikTok/Shorts/Reels)" if ar != "9:16" else "",
            )
        )

        # 6. Pace Variation
        variance = 0.0
        if len(timeline) >= 2:
            durations = [e.end_time - e.start_time for e in timeline]
            avg_dur = sum(durations) / len(durations)
            variance = sum((d - avg_dur) ** 2 for d in durations) / len(durations)
            pace_score = min(1.0, variance * 5.0)
        else:
            pace_score = 0.3
        criteria.append(
            _make_criterion(
                "Pace Variation",
                pace_score,
                f"Shot duration variance: {variance:.2f}" if len(timeline) >= 2 else "Single shot — no variation",
                "Vary shot durations for dynamic pacing (mix 2-5s with 8-12s shots)"
                if pace_score < 0.5
                else "",
            )
        )

        overall_score = round(sum(c.score for c in criteria) / len(criteria), 2)
        return AuditReport(
            audit_id=f"AUDIT-EDIT-{composition.script_id}",
            checkpoint=AuditCheckpoint.EDIT,
            target_artifact_id=composition.script_id,
            overall_score=overall_score,
            overall_status=_overall_status(criteria),
            criteria=criteria,
            summary=f"Edit '{composition.script_id}' audit: {overall_score:.0%} overall.",
        )

    def audit_thumbnail(
        self,
        thumbnail_set: ThumbnailSet,
        brand_guidelines: dict[str, Any] | None = None,
    ) -> AuditReport:
        """Audit a thumbnail set against 6 criteria."""
        criteria: list[AuditCriterion] = []
        variants = thumbnail_set.variants

        # 1. Variant Diversity
        concepts = {v.concept for v in variants}
        diversity_score = min(1.0, len(concepts) / 4.0)
        criteria.append(
            _make_criterion(
                "Variant Diversity",
                diversity_score,
                f"{len(concepts)} unique concepts out of {len(variants)} variants",
                "Each variant should explore a different visual concept"
                if len(concepts) < 3
                else "",
            )
        )

        # 2. CTR Potential
        all_text = " ".join((v.concept + " " + v.prompt).lower() for v in variants)
        ctr_keywords = ["curios", "question", "emotion", "contrast", "before/after", "bold"]
        matched_ctr = sum(1 for kw in ctr_keywords if kw in all_text)
        ctr_score = min(1.0, matched_ctr / 3.0)
        criteria.append(
            _make_criterion(
                "CTR Potential",
                ctr_score,
                f"CTR signals: {matched_ctr}/3 (curiosity, question, emotion)",
                "Use at least one: curiosity gap, question hook, or emotional contrast"
                if matched_ctr < 1
                else "",
            )
        )

        # 3. Brand Presence
        brand_color = brand_guidelines.get("brand_color", "") if brand_guidelines else ""
        brand_score = 0.5
        if brand_color:
            brand_score = 1.0 if brand_color.lower() in all_text else 0.5
        criteria.append(
            _make_criterion(
                "Brand Presence",
                brand_score,
                f"Brand color '{brand_color}' in prompts: {brand_color.lower() in all_text}" if brand_color
                else "No brand guidelines provided for brand presence check",
            )
        )

        # 4. Text Readability
        text_count = sum(1 for v in variants if '"' in v.prompt)
        readability_score = min(1.0, text_count / 2.0)
        criteria.append(
            _make_criterion(
                "Text Readability",
                readability_score,
                f"{text_count}/{len(variants)} variants include text overlays",
                "At least 2 variants should include text overlay elements"
                if text_count < 2
                else "",
            )
        )

        # 5. Platform Compliance
        banned_thumbnail = ["weapon", "violence", "gore", "nudity", "blood"]
        found_banned = [t for t in banned_thumbnail if t in all_text]
        compliance_score = 0.0 if found_banned else 1.0
        criteria.append(
            _make_criterion(
                "Platform Compliance",
                compliance_score,
                f"Banned content found: {', '.join(found_banned)}" if found_banned else "No banned content detected",
                "Remove references to violence, gore, nudity, or weapons"
                if found_banned
                else "",
            )
        )

        # 6. Visual Contrast
        contrast_keywords = ["contrast", "bold", "vibrant", "dark", "bright", "high contrast"]
        matched_contrast = sum(1 for kw in contrast_keywords if kw in all_text)
        contrast_score = min(1.0, matched_contrast / 3.0)
        criteria.append(
            _make_criterion(
                "Visual Contrast",
                contrast_score,
                f"Contrast signals: {matched_contrast}/3 (bold, vibrant, high contrast)",
                "Use at least 2 visual contrast techniques (bold, vibrant, dark/light)"
                if matched_contrast < 2
                else "",
            )
        )

        overall_score = round(sum(c.score for c in criteria) / len(criteria), 2)
        return AuditReport(
            audit_id=f"AUDIT-THUMB-{thumbnail_set.script_id}",
            checkpoint=AuditCheckpoint.THUMBNAIL,
            target_artifact_id=thumbnail_set.script_id,
            overall_score=overall_score,
            overall_status=_overall_status(criteria),
            criteria=criteria,
            summary=f"Thumbnail '{thumbnail_set.script_id}' audit: {overall_score:.0%} overall.",
        )

    @staticmethod
    def _score_hook_text(text: str) -> float:
        """Score hook text quality based on curiosity gap + pattern interrupt signals.

        Returns a 0-1 score. Tuned for English short-form video hooks.

        Curiosity gap signals (question/number/contrast/negation):
        - Question words: what, how, why, did you know, ever wondered
        - Numbers: any digit (creates specificity)
        - Contrast: but, however, yet, surprisingly
        - Negation: never, stop, don't, avoid, mistake

        Pattern interrupt signals (breaks viewer autopilot):
        - Direct address: you, your
        - Command: stop, wait, listen, look, watch
        - Shock: wrong, lie, myth, truth, secret
        - Urgency: now, today, immediately

        Scoring:
        - 0 signals = 0.2 (weak hook)
        - 1-2 signals = 0.5 (average hook)
        - 3-4 signals = 0.8 (strong hook)
        - 5+ signals = 1.0 (excellent hook)
        """
        if not text or len(text.strip()) < 3:
            return 0.0

        t = text.lower()
        signals = 0

        # Curiosity gap
        curiosity_patterns = [
            r"\bwhat\b", r"\bhow\b", r"\bwhy\b", r"\bwho\b",
            r"\bdid you know\b", r"\bever wondered\b", r"\bhere's why\b",
            r"\bthe reason\b", r"\bthe truth about\b", r"\bsecret\b",
        ]
        for pat in curiosity_patterns:
            if re.search(pat, t):
                signals += 1
                break  # only count once per category

        # Number specificity
        if re.search(r"\d", t):
            signals += 1

        # Contrast / surprise
        contrast_patterns = [r"\bbut\b", r"\bhowever\b", r"\byet\b", r"\bsurprisingly\b", r"\bunexpected\b"]
        for pat in contrast_patterns:
            if re.search(pat, t):
                signals += 1
                break

        # Pattern interrupt — direct command
        command_patterns = [r"\bstop\b", r"\bwait\b", r"\blisten\b", r"\blook\b", r"\bwatch\b"]
        for pat in command_patterns:
            if re.search(pat, t):
                signals += 1
                break

        # Pattern interrupt — shock / revelation
        shock_patterns = [r"\bwrong\b", r"\blie\b", r"\bmyth\b", r"\bmistake\b", r"\bnever\b", r"\bdon't\b"]
        for pat in shock_patterns:
            if re.search(pat, t):
                signals += 1
                break

        # Urgency
        if re.search(r"\bnow\b|\btoday\b|\bimmediately\b", t):
            signals += 1

        # Direct address (second person)
        if re.search(r"\byou\b|\byour\b", t):
            signals += 1

        if signals >= 5:
            return 1.0
        if signals >= 3:
            return 0.8
        if signals >= 1:
            return 0.5
        return 0.2

    @staticmethod
    def _score_emotional_arc(segments: list[Any]) -> dict[str, Any]:
        """Evaluate emotional progression through the script.

        Target arc for short-form video (AIDA-inspired):
        attention/grab → problem/negative → solution/positive → trust/reinforce → urgency/CTA

        Checks:
        1. Has a pain_point followed by solution (negative → positive transition)
        2. CTA segment contains urgency signals (now, today, click, get, buy)
        3. Hook segment has attention-grabbing signals (question, command)

        Returns dict with score, observation, recommendation.
        """

        def _get_field(seg: Any, key: str) -> str:
            if isinstance(seg, dict):
                return seg.get(key, "")
            return getattr(seg, key, "") or ""

        # Build observed valence sequence
        observed: list[str] = []
        for seg in segments:
            st = _get_field(seg, "segment_type")
            val = AuditorAgent._VALENCE_MAP.get(st, "neutral")
            if val != "neutral":
                observed.append(val)

        if not observed:
            return {
                "score": 0.3,
                "observation": "No recognizable emotional segments found",
                "recommendation": "Include segments with clear emotional purpose (problem → solution → CTA)",
            }

        checks_passed = 0.0
        checks_total = 3
        observations: list[str] = []

        # Check 1: negative → positive transition (problem/solution arc)
        neg_before_pos = False
        for i, v in enumerate(observed):
            if v == "negative":
                if any(observed[j] == "positive" for j in range(i + 1, len(observed))):
                    neg_before_pos = True
                    break
        if neg_before_pos:
            checks_passed += 1
            observations.append("negative→positive arc present")
        elif any(v == "negative" for v in observed) and any(v == "positive" for v in observed):
            checks_passed += 0.5
            observations.append("both negative and positive present but not in sequence")
        else:
            observations.append("missing negative→positive arc")

        # Check 2: urgency at CTA
        cta_segments = [seg for seg in segments if _get_field(seg, "segment_type") == "cta"]
        urgency_words = ["now", "today", "immediately", "click", "get", "buy", "order", "limited", "hurry"]
        has_urgency = False
        for cta in cta_segments:
            text = _get_field(cta, "voiceover").lower()
            if any(w in text for w in urgency_words):
                has_urgency = True
                break
        if has_urgency:
            checks_passed += 1
            observations.append("CTA contains urgency signals")
        else:
            observations.append("CTA lacks urgency — add 'now', 'today', or 'click'")

        # Check 3: hook attention signal
        hook_segments = [seg for seg in segments if _get_field(seg, "segment_type") == "hook"]
        attention_words = ["what", "how", "why", "stop", "wait", "mistake", "never", "secret", "truth"]
        has_attention = False
        for h in hook_segments:
            text = _get_field(h, "voiceover").lower()
            if any(w in text for w in attention_words):
                has_attention = True
                break
        if has_attention:
            checks_passed += 1
            observations.append("hook has attention-grabbing signals")
        else:
            observations.append("hook lacks attention signals — use question or command")

        score = checks_passed / checks_total
        if score >= 0.8:
            recommendation = ""
        elif score >= 0.5:
            recommendation = "Strengthen emotional arc: ensure clear problem→solution sequence"
        else:
            recommendation = "Restructure script with attention hook, problem/solution contrast, and urgent CTA"

        return {
            "score": round(score, 2),
            "observation": "; ".join(observations),
            "recommendation": recommendation,
        }
