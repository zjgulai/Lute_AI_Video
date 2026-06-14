"""Test Pydantic state models — schema validation."""

from src.models import (
    Brief,
    ComplianceFlag,
    ComplianceReport,
    ComplianceStatus,
    Language,
    Platform,
    Script,
    ScriptSegment,
    Severity,
    Shot,
    Storyboard,
    VideoType,
    WeeklyCalendar,
)


class TestBrief:
    def test_brief_creation(self):
        brief = Brief(
            id="BRIEF-001",
            video_type=VideoType.TUTORIAL,
            topic="How to clean wearable pump",
            target_audience="Working moms 25-35",
            target_platforms=[Platform.TIKTOK],
            target_languages=[Language.EN],
            key_message="Discreet cleaning",
            usp_priority=["portable", "quiet"],
        )
        assert brief.id == "BRIEF-001"
        assert brief.video_type == VideoType.TUTORIAL
        assert len(brief.usp_priority) == 2

    def test_weekly_calendar(self):
        brief = Brief(
            id="BRIEF-001",
            video_type=VideoType.UNBOXING,
            topic="Test",
            target_audience="Test",
            target_platforms=[Platform.TIKTOK],
            target_languages=[Language.EN],
            key_message="Test",
            usp_priority=["test"],
        )
        cal = WeeklyCalendar(week="2026-W17", briefs=[brief])
        assert cal.week == "2026-W17"
        assert len(cal.briefs) == 1


class TestScript:
    def test_script_creation(self):
        seg = ScriptSegment(
            segment_type="hook",
            start_time=0.0,
            end_time=3.0,
            voiceover="Test hook",
            visual_description="Test visual",
            text_overlay="Test text",
        )
        script = Script(
            id="SCRIPT-001",
            brief_id="BRIEF-001",
            platform=Platform.TIKTOK,
            language=Language.EN,
            total_duration=45.0,
            segments=[seg],
            hashtags=["#test"],
            cta_text="Link in bio",
        )
        assert script.total_duration == 45.0
        assert len(script.segments) == 1
        assert script.segments[0].segment_type == "hook"


class TestCompliance:
    def test_compliance_report_pass(self):
        report = ComplianceReport(
            script_id="SCRIPT-001",
            status=ComplianceStatus.PASS,
            flags=[],
        )
        assert report.status == ComplianceStatus.PASS

    def test_compliance_report_flagged(self):
        flag = ComplianceFlag(
            severity=Severity.HIGH,
            line_index=0,
            text="prevents mastitis",
            issue="Medical claim",
            suggestion="Rephrase",
        )
        report = ComplianceReport(
            script_id="SCRIPT-001",
            status=ComplianceStatus.FLAGGED,
            flags=[flag],
        )
        assert report.status == ComplianceStatus.FLAGGED
        assert len(report.flags) == 1
        assert report.flags[0].severity == Severity.HIGH


class TestStoryboard:
    def test_storyboard_creation(self):
        shot = Shot(
            id=1,
            start_time=0.0,
            end_time=2.5,
            shot_type="hook",
            visual="Opening shot",
            text_overlay="Pumping at work?",
            camera="Static",
            asset_needed="B-Roll: office",
        )
        sb = Storyboard(
            script_id="SCRIPT-001",
            total_duration=45.0,
            shots=[shot],
        )
        assert sb.aspect_ratio == "9:16"
        assert len(sb.shots) == 1
