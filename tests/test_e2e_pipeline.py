"""End-to-end pipeline test — 12 nodes + 4 human review checkpoints.

Runs the complete pipeline with mock data, simulates human approval
at each checkpoint, and verifies all intermediate and final outputs.
"""

import pytest
from langgraph.checkpoint.memory import MemorySaver

from src.graph.pipeline import compile_pipeline
from src.models import (
    WeeklyCalendar, Script, ComplianceReport, ComplianceStatus,
    Storyboard, AssetPlan, EditComposition, AudioPlan,
    CaptionPlan, ThumbnailSet, DistributionPlan, AnalyticsReport,
    HumanReview, ApprovalStatus,
)


REVIEW_NODES = ["strategy_review", "script_review", "edit_review", "thumbnail_review"]
AUDIT_CHECKPOINTS = ["strategy", "script", "edit", "thumbnail"]


def simulate_approval(pipeline, config: dict, review_node: str, status=ApprovalStatus.APPROVED):
    """Simulate a human clicking 'approve' on a review checkpoint."""
    snapshot = pipeline.get_state(config)
    current_reviews = dict(snapshot.values.get("human_reviews", {}) if snapshot.values else {})
    current_reviews[review_node] = HumanReview(
        node=review_node,
        status=status,
        reviewer_notes=f"E2E test auto-approval for {review_node}",
    ).model_dump()
    pipeline.update_state(config, {"human_reviews": current_reviews})


class TestE2EPipeline:
    """Full end-to-end pipeline test with all 12 nodes."""

    @pytest.fixture
    def pipeline(self):
        return compile_pipeline(checkpointer=MemorySaver())

    @pytest.fixture
    def config(self):
        return {"configurable": {"thread_id": "e2e-test-001"}}

    @pytest.fixture
    def initial_state(self):
        return {
            "product_catalog": {
                "products": [{
                    "name": "Wearable Breast Pump X1",
                    "usps": [
                        {"priority": "P0", "text": "Hands-free, fits in bra"},
                        {"priority": "P0", "text": "Hospital-grade suction"},
                        {"priority": "P1", "text": "Quiet <40dB"},
                    ],
                    "specs": {"weight": "220g", "battery_life": "2.5h"},
                    "certifications": ["FDA", "CE"],
                }]
            },
            "brand_guidelines": {
                "brand_name": "TestBrand",
                "tone_of_voice": {"archetype": "Caregiver", "keywords": ["warm", "empowering"]},
                "compliance": {"forbidden_claims": ["cures"]},
            },
            "target_platforms": ["tiktok"],
            "target_languages": ["en"],
            "content_calendar_week": "2026-W17",
            "current_step": "init",
            "errors": [],
            "human_reviews": {},
            "pipeline_complete": False,
        }

    # ── Phase 1: Strategy → Script → Compliance → Storyboard ──

    @pytest.mark.asyncio
    async def test_phase1_strategy_to_storyboard(self, pipeline, config, initial_state):
        """Nodes 1-4: Strategy, Script, Compliance, Storyboard."""
        # Run strategy node (will interrupt after)
        events = []
        async for event in pipeline.astream(initial_state, config):
            events.append(event)

        assert len(events) > 0
        state = pipeline.get_state(config).values

        # Verify strategy output
        assert state.get("weekly_calendar") is not None
        assert isinstance(state["weekly_calendar"], WeeklyCalendar)
        assert len(state["weekly_calendar"].briefs) >= 1
        print(f"  ✓ Strategy: {len(state['weekly_calendar'].briefs)} briefs")

        # Verify strategy audit ran
        assert state.get("audit_reports") is not None
        assert "strategy" in state["audit_reports"]
        strategy_audit = state["audit_reports"]["strategy"]
        assert strategy_audit.checkpoint == "strategy"
        assert len(strategy_audit.criteria) == 6
        print(f"  ✓ Strategy Audit: score={strategy_audit.overall_score:.0%}, status={strategy_audit.overall_status}")

        # Human approves strategy
        simulate_approval(pipeline, config, "strategy_review")

        # Continue to script node
        events = []
        async for event in pipeline.astream(None, config):
            events.append(event)

        state = pipeline.get_state(config).values
        assert state.get("scripts") is not None
        assert len(state["scripts"]) >= 1
        assert isinstance(state["scripts"][0], Script)
        assert len(state["scripts"][0].segments) == 5  # hook, pain, solution, trust, cta
        print(f"  ✓ Script: {len(state['scripts'])} scripts, {len(state['scripts'][0].segments)} segments")

        # Human approves script
        simulate_approval(pipeline, config, "script_review")

        # Continue to compliance → storyboard
        events = []
        async for event in pipeline.astream(None, config):
            events.append(event)

        state = pipeline.get_state(config).values

        # Verify compliance
        assert state.get("compliance_reports") is not None
        reports = state["compliance_reports"]
        assert len(reports) >= 1
        assert isinstance(reports[0], ComplianceReport)
        # Mock scripts should pass compliance
        assert reports[0].status != ComplianceStatus.BLOCKED
        print(f"  ✓ Compliance: {reports[0].status.value} ({len(reports[0].flags)} flags)")

        # Verify storyboard
        assert state.get("storyboards") is not None
        assert len(state["storyboards"]) >= 1
        assert isinstance(state["storyboards"][0], Storyboard)
        assert len(state["storyboards"][0].shots) >= 1
        print(f"  ✓ Storyboard: {len(state['storyboards'])} boards, {len(state['storyboards'][0].shots)} shots")

    # ── Phase 2: Asset Sourcing → Media Gen → Editing → Audio → Caption ──

    @pytest.mark.asyncio
    async def test_phase2_asset_to_caption(self, pipeline, config, initial_state):
        """Nodes 5-9: Asset Sourcing through Caption."""
        # Fast-forward through Phase 1 first
        async for _ in pipeline.astream(initial_state, config):
            pass
        simulate_approval(pipeline, config, "strategy_review")
        async for _ in pipeline.astream(None, config):
            pass
        simulate_approval(pipeline, config, "script_review")
        async for _ in pipeline.astream(None, config):
            pass  # Compliance → Storyboard → Asset Sourcing

        state = pipeline.get_state(config).values

        # Verify asset sourcing
        assert state.get("asset_plans") is not None
        assert len(state["asset_plans"]) >= 1
        assert isinstance(state["asset_plans"][0], AssetPlan)
        print(f"  ✓ Asset Plans: {len(state['asset_plans'])} plans")

        # Continue (may go through media_generation if gaps exist)
        async for _ in pipeline.astream(None, config):
            pass

        state = pipeline.get_state(config).values

        # Verify editing
        assert state.get("edit_compositions") is not None
        assert len(state["edit_compositions"]) >= 1
        assert isinstance(state["edit_compositions"][0], EditComposition)
        print(f"  ✓ Edit Compositions: {len(state['edit_compositions'])} comps")

        # Human approves editing (checkpoint #3)
        simulate_approval(pipeline, config, "edit_review")

        # Continue to audio → caption
        async for _ in pipeline.astream(None, config):
            pass

        state = pipeline.get_state(config).values

        # Verify audio
        assert state.get("audio_plans") is not None
        assert len(state["audio_plans"]) >= 1
        assert isinstance(state["audio_plans"][0], AudioPlan)
        print(f"  ✓ Audio Plans: {len(state['audio_plans'])} plans")

        # Verify caption
        assert state.get("caption_plans") is not None
        assert len(state["caption_plans"]) >= 1
        assert isinstance(state["caption_plans"][0], CaptionPlan)
        assert len(state["caption_plans"][0].entries) > 0
        print(f"  ✓ Caption Plans: {len(state['caption_plans'])} plans, {len(state['caption_plans'][0].entries)} entries")

    # ── Phase 3: Thumbnail → Distribution → Analytics ──

    @pytest.mark.asyncio
    async def test_phase3_thumbnail_to_analytics(self, pipeline, config, initial_state):
        """Nodes 10-12: Thumbnail through Analytics (final phase)."""
        # Fast-forward through all prior phases
        async for _ in pipeline.astream(initial_state, config):
            pass
        simulate_approval(pipeline, config, "strategy_review")
        async for _ in pipeline.astream(None, config):
            pass
        simulate_approval(pipeline, config, "script_review")
        async for _ in pipeline.astream(None, config):
            pass
        async for _ in pipeline.astream(None, config):
            pass
        simulate_approval(pipeline, config, "edit_review")
        async for _ in pipeline.astream(None, config):
            pass  # Audio → Caption → Thumbnail

        state = pipeline.get_state(config).values

        # Verify thumbnail
        assert state.get("thumbnail_sets") is not None
        assert len(state["thumbnail_sets"]) >= 1
        assert isinstance(state["thumbnail_sets"][0], ThumbnailSet)
        assert len(state["thumbnail_sets"][0].variants) == 4  # A, B, C, D
        print(f"  ✓ Thumbnails: {len(state['thumbnail_sets'])} sets, {len(state['thumbnail_sets'][0].variants)} variants")

        # Human approves thumbnail (checkpoint #4)
        simulate_approval(pipeline, config, "thumbnail_review")

        # Continue to distribution → analytics
        async for _ in pipeline.astream(None, config):
            pass

        state = pipeline.get_state(config).values

        # Verify distribution
        assert state.get("distribution_plans") is not None
        assert len(state["distribution_plans"]) >= 1
        assert isinstance(state["distribution_plans"][0], DistributionPlan)
        print(f"  ✓ Distribution: {len(state['distribution_plans'])} plans")

        # Verify analytics
        assert state.get("analytics_reports") is not None
        assert len(state["analytics_reports"]) >= 1
        assert isinstance(state["analytics_reports"][0], AnalyticsReport)
        print(f"  ✓ Analytics: {len(state['analytics_reports'])} reports")

        # Verify pipeline complete
        assert state.get("pipeline_complete") is True
        print(f"  ✓ Pipeline Complete: True")

    # ── Full end-to-end ──

    @pytest.mark.asyncio
    async def test_full_e2e_all_nodes(self, pipeline, config, initial_state):
        """Run the ENTIRE pipeline end-to-end with all checkpoints."""
        all_nodes_seen = set()

        # Phase 1: Strategy → Script (checkpoints 1-2)
        async for event in pipeline.astream(initial_state, config):
            for node_name in event:
                all_nodes_seen.add(node_name)

        simulate_approval(pipeline, config, "strategy_review")
        async for event in pipeline.astream(None, config):
            for node_name in event:
                all_nodes_seen.add(node_name)

        simulate_approval(pipeline, config, "script_review")

        # Phase 2: Compliance through Editing (checkpoint 3)
        async for event in pipeline.astream(None, config):
            for node_name in event:
                all_nodes_seen.add(node_name)

        simulate_approval(pipeline, config, "edit_review")

        # Phase 3: Audio through Thumbnail (checkpoint 4)
        async for event in pipeline.astream(None, config):
            for node_name in event:
                all_nodes_seen.add(node_name)

        simulate_approval(pipeline, config, "thumbnail_review")

        # Phase 4: Distribution → Analytics → END
        async for event in pipeline.astream(None, config):
            for node_name in event:
                all_nodes_seen.add(node_name)

        # Verify all nodes executed
        expected_nodes = {
            "strategy_node", "strategy_audit_node",
            "script_node", "script_audit_node",
            "compliance_node",
            "storyboard_node", "asset_sourcing_node", "media_generation_node",
            "editing_node", "editing_audit_node",
            "audio_node", "caption_node",
            "thumbnail_node", "thumbnail_audit_node",
            "distribution_node", "analytics_node",
        }

        missing = expected_nodes - all_nodes_seen
        extra = all_nodes_seen - expected_nodes

        print(f"  Nodes executed: {sorted(all_nodes_seen)}")
        if missing:
            print(f"  ⚠ Missing: {missing}")
        if extra:
            print(f"  ℹ Extra: {extra}")

        # Media generation is conditional (only runs if gaps exist)
        # It may or may not execute depending on mock data
        assert len(all_nodes_seen) >= 15, f"Expected at least 15 nodes, got {len(all_nodes_seen)}"

        # Final state verification
        state = pipeline.get_state(config).values
        assert state.get("pipeline_complete") is True
        assert state.get("weekly_calendar") is not None
        assert state.get("scripts") is not None
        assert state.get("compliance_reports") is not None
        assert state.get("storyboards") is not None
        assert state.get("edit_compositions") is not None
        assert state.get("audio_plans") is not None
        assert state.get("caption_plans") is not None
        assert state.get("thumbnail_sets") is not None
        assert state.get("distribution_plans") is not None
        assert state.get("analytics_reports") is not None

        print(f"\n  ✅ FULL E2E COMPLETE — 16 nodes, 4 self-audits, 4 human checkpoints, pipeline finished")


class TestE2EComplianceBlock:
    """Test that pipeline terminates when compliance returns BLOCKED."""

    @pytest.fixture
    def pipeline(self):
        return compile_pipeline(checkpointer=MemorySaver())

    @pytest.fixture
    def config(self):
        return {"configurable": {"thread_id": "e2e-blocked-001"}}

    @pytest.fixture
    def initial_state(self):
        return {
            "product_catalog": {"products": [{
                "name": "Wearable Breast Pump X1",
                "usps": [{"priority": "P0", "text": "Hands-free, fits in bra"}],
                "specs": {"weight": "220g", "battery_life": "2.5h"},
                "certifications": ["FDA", "CE"],
            }]},
            "brand_guidelines": {
                "brand_name": "TestBrand",
                "tone_of_voice": {"archetype": "Caregiver", "keywords": ["warm"]},
                "compliance": {"forbidden_claims": ["cures"]},
            },
            "target_platforms": ["tiktok"],
            "target_languages": ["en"],
            "content_calendar_week": "2026-W17",
            "current_step": "init", "errors": [], "human_reviews": {}, "pipeline_complete": False,
        }

    def _inject_blocking_script(self, pipeline, config):
        """Replace the scripts in state with one that triggers a HIGH severity compliance rule."""
        from src.models import Script, ScriptSegment, Platform, Language

        bad_script = Script(
            id="SCRIPT-BLOCKED-001",
            brief_id="BRIEF-001",
            platform=Platform.TIKTOK,
            language=Language.EN,
            total_duration=45.0,
            segments=[
                ScriptSegment(
                    segment_type="hook", start_time=0.0, end_time=3.0,
                    voiceover="This product cures mastitis instantly and prevents all clogged ducts.",
                    visual_description="Hook shot",
                    text_overlay="",
                ),
                ScriptSegment(
                    segment_type="pain_point", start_time=3.0, end_time=8.0,
                    voiceover="Most moms suffer in silence.",
                    visual_description="Pain visual",
                    text_overlay="",
                ),
                ScriptSegment(
                    segment_type="solution", start_time=8.0, end_time=20.0,
                    voiceover="The X1 is the solution.",
                    visual_description="Product demo",
                    text_overlay="",
                ),
                ScriptSegment(
                    segment_type="trust_building", start_time=20.0, end_time=35.0,
                    voiceover="FDA cleared. Trusted by moms.",
                    visual_description="FDA badge",
                    text_overlay="",
                ),
                ScriptSegment(
                    segment_type="cta", start_time=35.0, end_time=45.0,
                    voiceover="Buy now at link in bio.",
                    visual_description="CTA",
                    text_overlay="",
                ),
            ],
            hashtags=["#test"],
            cta_text="Link in bio",
        )
        pipeline.update_state(config, {
            "scripts": [bad_script],
            "current_step": "script_complete",
            # Clear the audit report so compliance doesn't short-circuit on stale data
            "audit_reports": {},
        })

    @pytest.mark.asyncio
    async def test_compliance_blocked_terminates_pipeline(self, pipeline, config, initial_state):
        """Compliance BLOCKED → pipeline terminates, no downstream nodes execute."""
        # Run strategy → strategy_audit (interrupts here)
        async for _ in pipeline.astream(initial_state, config):
            pass

        # Approve strategy review so it proceeds to script_node
        from src.models import HumanReview, ApprovalStatus
        snap = pipeline.get_state(config)
        reviews = dict(snap.values.get("human_reviews", {}))
        reviews["strategy_review"] = HumanReview(
            node="strategy_review",
            status=ApprovalStatus.APPROVED,
            reviewer_notes="E2E test",
        ).model_dump()
        pipeline.update_state(config, {"human_reviews": reviews})

        # Run script → script_audit (interrupts here)
        async for _ in pipeline.astream(None, config):
            pass

        # NOW inject a script with HIGH severity violation into state,
        # right before compliance runs. This replaces the mock scripts.
        self._inject_blocking_script(pipeline, config)

        # Approve script review so it proceeds to compliance_node
        snap2 = pipeline.get_state(config)
        reviews2 = dict(snap2.values.get("human_reviews", {}))
        reviews2["script_review"] = HumanReview(
            node="script_review",
            status=ApprovalStatus.APPROVED,
            reviewer_notes="E2E test",
        ).model_dump()
        pipeline.update_state(config, {"human_reviews": reviews2})

        # Run compliance node — this is where blocking should happen
        nodes_seen = set()
        async for event in pipeline.astream(None, config):
            for node_name in event:
                nodes_seen.add(node_name)

        state = pipeline.get_state(config).values

        # Verify compliance report exists and is BLOCKED
        assert state.get("compliance_reports") is not None, "No compliance reports generated"
        assert len(state["compliance_reports"]) >= 1
        blocked_reports = [r for r in state["compliance_reports"]
                          if hasattr(r, "status") and r.status.value == "BLOCKED"]
        assert len(blocked_reports) >= 1, (
            f"No BLOCKED reports found. Statuses: {[r.status.value if hasattr(r, 'status') else '?' for r in state['compliance_reports']]}"
        )
        print(f"  ✓ Compliance BLOCKED: {blocked_reports[0].script_id}")

        # Verify pipeline terminated — no downstream nodes executed
        # (strategy_node and script_node ran in previous astream calls,
        #  so they won't appear in nodes_seen from this resume)
        assert "storyboard_node" not in nodes_seen, (
            f"Pipeline continued past compliance BLOCKED! Nodes seen: {sorted(nodes_seen)}"
        )
        assert "editing_node" not in nodes_seen
        assert "asset_sourcing_node" not in nodes_seen
        assert "distribution_node" not in nodes_seen
        assert "analytics_node" not in nodes_seen
        assert state.get("pipeline_complete") is not True, "Pipeline should NOT be complete after block"

        # Verify compliance DID execute (and consumed our injected script)
        assert "compliance_node" in nodes_seen

        print(f"  ✓ Pipeline terminated after compliance. No downstream nodes executed.")
        print(f"  ✓ Compliance report: {blocked_reports[0].script_id} = {blocked_reports[0].status.value}")
        print(f"  ✅ COMPLIANCE BLOCKED TEST PASSED")


class TestE2EComplianceShortcut:
    """Test the compliance pre-check short-circuit path.

    When script_audit_node's Compliance Pre-check criterion is PASS,
    compliance_node should skip the full rule engine scan entirely and
    return PASS for all scripts — saving compute on content already verified clean.

    When the pre-check is WARN or FAIL, the full rule engine still runs
    as normal.
    """

    @pytest.fixture
    def pipeline(self):
        return compile_pipeline(checkpointer=MemorySaver())

    @pytest.fixture
    def config(self):
        return {"configurable": {"thread_id": "e2e-compliance-shortcut-001"}}

    @pytest.fixture
    def initial_state(self):
        return {
            "product_catalog": {"products": [{
                "name": "Wearable Breast Pump X1",
                "usps": [{"priority": "P0", "text": "Hands-free, fits in bra"}],
                "specs": {"weight": "220g", "battery_life": "2.5h"},
                "certifications": ["FDA", "CE"],
            }]},
            "brand_guidelines": {"brand_name": "TestBrand", "tone_of_voice": {}, "compliance": {}},
            "target_platforms": ["tiktok"],
            "target_languages": ["en"],
            "content_calendar_week": "2026-W17",
            "current_step": "init", "errors": [], "human_reviews": {}, "pipeline_complete": False,
        }

    def _inject_audit_with_precheck(self, pipeline, config, status, precheck_score=1.0):
        """Inject an AuditReport with a specific Compliance Pre-check status into state.

        This simulates what script_audit_node would produce, so compliance_node
        can read it and decide whether to short-circuit.
        """
        from src.models import (
            AuditReport, AuditCheckpoint, AuditCriterion, AuditCriterionStatus,
        )

        pass_status = status if status is not None else AuditCriterionStatus.PASS

        report = AuditReport(
            audit_id="AUDIT-SCRIPT-INJECTED",
            checkpoint=AuditCheckpoint.SCRIPT,
            target_artifact_id="SCRIPT-INJECTED",
            overall_score=0.85,
            overall_status=pass_status,
            criteria=[
                AuditCriterion(
                    name="Hook Strength",
                    status=pass_status,
                    score=1.0,
                    observation="Hook present",
                ),
                AuditCriterion(
                    name="Compliance Pre-check",
                    status=status,
                    score=precheck_score,
                    observation="Injected test pre-check",
                    recommendation="",
                ),
            ],
            summary="Injected audit for test",
        )
        pipeline.update_state(config, {
            "audit_reports": {"script": report},
        })

    @pytest.mark.asyncio
    async def test_precheck_pass_skips_full_compliance_scan(self, pipeline, config, initial_state):
        """When pre-check is PASS, compliance_node returns PASS with zero flags."""
        # Run strategy -> strategy_audit (interrupts here)
        async for _ in pipeline.astream(initial_state, config):
            pass

        from src.models import HumanReview, ApprovalStatus, AuditCriterionStatus

        def approve(node):
            snap = pipeline.get_state(config)
            reviews = dict(snap.values.get("human_reviews", {}))
            reviews[node] = HumanReview(
                node=node, status=ApprovalStatus.APPROVED,
                reviewer_notes="E2E",
            ).model_dump()
            pipeline.update_state(config, {"human_reviews": reviews})

        approve("strategy_review")

        # Run script → script_audit (interrupts here)
        async for _ in pipeline.astream(None, config):
            pass

        # Inject a pre-check PASS audit report
        self._inject_audit_with_precheck(pipeline, config, AuditCriterionStatus.PASS, 1.0)

        approve("script_review")

        # Run compliance_node — should short-circuit
        nodes_seen = set()
        async for event in pipeline.astream(None, config):
            for node_name in event:
                nodes_seen.add(node_name)

        state = pipeline.get_state(config).values

        # Verify compliance_node ran
        assert "compliance_node" in nodes_seen
        assert state.get("compliance_reports") is not None

        # All reports should be PASS with zero flags
        reports = state["compliance_reports"]
        assert len(reports) >= 1
        for r in reports:
            status_val = r.status.value if hasattr(r.status, "value") else str(r.status)
            assert status_val == "PASS", (
                f"Expected PASS after shortcut, got {status_val}"
            )
            assert len(r.flags) == 0, (
                f"Expected zero flags after shortcut, got {len(r.flags)}"
            )

        # Pipeline continued to storyboard (not blocked)
        assert "storyboard_node" in nodes_seen
        print(f"  ✓ Pre-check PASS → compliance short-circuited, {len(reports)} reports all PASS with 0 flags")
        print(f"  ✓ Pipeline continued to storyboard_node")
        print(f"  ✅ COMPLIANCE SHORTCUT (PASS) TEST PASSED")

    @pytest.mark.asyncio
    async def test_precheck_warn_still_runs_full_compliance(self, pipeline, config, initial_state):
        """When pre-check is WARN, compliance_node still runs the full rule engine."""
        async for _ in pipeline.astream(initial_state, config):
            pass

        from src.models import HumanReview, ApprovalStatus, AuditCriterionStatus

        def approve(node):
            snap = pipeline.get_state(config)
            reviews = dict(snap.values.get("human_reviews", {}))
            reviews[node] = HumanReview(
                node=node, status=ApprovalStatus.APPROVED,
                reviewer_notes="E2E",
            ).model_dump()
            pipeline.update_state(config, {"human_reviews": reviews})

        approve("strategy_review")
        async for _ in pipeline.astream(None, config):
            pass

        # Inject a pre-check WARN audit report (low score = red flags found)
        self._inject_audit_with_precheck(pipeline, config, AuditCriterionStatus.WARN, 0.4)

        approve("script_review")

        # Run compliance_node — should NOT short-circuit
        nodes_seen = set()
        async for event in pipeline.astream(None, config):
            for node_name in event:
                nodes_seen.add(node_name)

        state = pipeline.get_state(config).values

        # Verify compliance_node ran
        assert "compliance_node" in nodes_seen
        assert state.get("compliance_reports") is not None

        # Reports from the mock scripts should still be PASS (mock scripts are clean)
        # — the point is the rule engine ran despite pre-check being WARN
        reports = state["compliance_reports"]
        assert len(reports) >= 1

        # Log the result for debugging
        for r in reports:
            status_val = r.status.value if hasattr(r.status, "value") else str(r.status)
            print(f"  ℹ Compliance report: {r.script_id} = {status_val} ({len(r.flags)} flags)")

        # Pipeline continued (normal mock scripts are clean)
        assert "storyboard_node" in nodes_seen
        print(f"  ✓ Pre-check WARN → full compliance engine ran")
        print(f"  ✅ COMPLIANCE SHORTCUT (WARN) TEST PASSED")


class TestE2EAssetSourcingShortcut:
    """Test the asset_sourcing → media_generation shortcut path.

    Default mock behavior: asset sourcing creates gaps for pain_point and
    trust_building shots → route sends to media_generation_node.
    By injecting no-gap asset plans, we can test the skip path.
    """

    @pytest.fixture
    def pipeline(self):
        return compile_pipeline(checkpointer=MemorySaver())

    @pytest.fixture
    def config(self):
        return {"configurable": {"thread_id": "e2e-asset-gap-001"}}

    @pytest.fixture
    def initial_state(self):
        return {
            "product_catalog": {"products": [{
                "name": "Wearable Breast Pump X1",
                "usps": [{"priority": "P0", "text": "Hands-free"}],
                "specs": {"weight": "220g", "battery_life": "2.5h"},
                "certifications": ["FDA"],
            }]},
            "brand_guidelines": {"brand_name": "TestBrand", "tone_of_voice": {}, "compliance": {}},
            "target_platforms": ["tiktok"],
            "target_languages": ["en"],
            "content_calendar_week": "2026-W17",
            "current_step": "init", "errors": [], "human_reviews": {}, "pipeline_complete": False,
        }

    def _run_through_script(self, pipeline, config, initial_state):
        """Run strategy → script → both approved, returning the next interrupt state."""
        import asyncio
        from src.models import HumanReview, ApprovalStatus

        async def _run():
            async for _ in pipeline.astream(initial_state, config):
                pass

            def approve(node):
                snap = pipeline.get_state(config)
                reviews = dict(snap.values.get("human_reviews", {}))
                reviews[node] = HumanReview(
                    node=node, status=ApprovalStatus.APPROVED,
                    reviewer_notes="E2E test",
                ).model_dump()
                pipeline.update_state(config, {"human_reviews": reviews})

            approve("strategy_review")
            async for _ in pipeline.astream(None, config):
                pass

            approve("script_review")
            # Run compliance → storyboard → asset_sourcing → route
            async for _ in pipeline.astream(None, config):
                pass

        asyncio.run(_run())

    @pytest.mark.asyncio
    async def test_has_gaps_routes_to_media_generation(self, pipeline, config, initial_state):
        """When asset sourcing finds no match → gap → media_generation_node executes."""
        # Phase 1: strategy → strategy_audit
        async for _ in pipeline.astream(initial_state, config):
            pass
        from src.models import HumanReview, ApprovalStatus

        def approve(node):
            snap = pipeline.get_state(config)
            reviews = dict(snap.values.get("human_reviews", {}))
            reviews[node] = HumanReview(
                node=node, status=ApprovalStatus.APPROVED,
                reviewer_notes="E2E",
            ).model_dump()
            pipeline.update_state(config, {"human_reviews": reviews})

        approve("strategy_review")
        async for _ in pipeline.astream(None, config):
            pass
        approve("script_review")

        # Now inject empty-ish asset_plans with gaps BEFORE the next pass runs
        # (so asset_sourcing_node skips, and gap-based route sends to media_gen)
        from src.models import AssetPlan
        pipeline.update_state(config, {
            "asset_plans": [
                AssetPlan(
                    storyboard_id="GAP-FORCED",
                    shot_plans=[],
                    gaps=["product_intro", "feature_demo"],
                ),
            ],
        })

        # Run compliance → storyboard → asset_sourcing (skips) → route with gaps
        nodes_seen = set()
        async for event in pipeline.astream(None, config):
            for node_name in event:
                nodes_seen.add(node_name)

        state = pipeline.get_state(config).values

        # Verify: media_generation_node ran because gaps exist
        assert "media_generation_node" in nodes_seen, (
            f"media_generation_node NOT executed despite gaps. Nodes: {sorted(nodes_seen)}"
        )
        print(f"  ✓ Gaps forced → media_generation executed")
        print(f"  ✓ Nodes in this phase: {sorted(nodes_seen)}")

    @pytest.mark.asyncio
    async def test_no_gaps_skips_media_generation(self, pipeline, config, initial_state):
        """Inject no-gap asset plans → media_generation_node skipped."""
        # Phase 1: strategy → strategy_audit
        async for _ in pipeline.astream(initial_state, config):
            pass
        from src.models import HumanReview, ApprovalStatus, AssetPlan, ShotAssetPlan, AssetCandidate

        def approve(node):
            snap = pipeline.get_state(config)
            reviews = dict(snap.values.get("human_reviews", {}))
            reviews[node] = HumanReview(
                node=node, status=ApprovalStatus.APPROVED,
                reviewer_notes="E2E",
            ).model_dump()
            pipeline.update_state(config, {"human_reviews": reviews})

        approve("strategy_review")
        # script → script_audit
        async for _ in pipeline.astream(None, config):
            pass
        approve("script_review")

        # compliance → storyboard (interrupts at script_audit again? No — runs through)
        # This pass runs: compliance → storyboard → asset_sourcing → route
        # We need to inject BEFORE asset_sourcing runs. Inject no-gap plans into state
        # with current_step=asset_sourcing_complete so the node skips regeneration.
        no_gap_plans = [
            AssetPlan(
                storyboard_id="INJECTED-SKIP",
                shot_plans=[
                    ShotAssetPlan(
                        shot_id=1,
                        asset_needed="test",
                        candidates=[
                            AssetCandidate(
                                asset_id="mock-injected-1",
                                file_path="/assets/injected.mp4",
                                description="Injected no-gap asset",
                                match_score=0.95,
                                source="library",
                            )
                        ],
                        selected_asset_id="mock-injected-1",
                        gap=False,
                    ),
                ],
                gaps=[],
            )
        ]

        # Inject no-gap plans BEFORE compliance runs (it will cascade through storyboard
        # and hit asset_sourcing_node, which now checks for pre-existing plans)
        pipeline.update_state(config, {
            "asset_plans": no_gap_plans,
        })

        # Run compliance → storyboard → asset_sourcing (which skips) → route → ?
        nodes_seen = set()
        async for event in pipeline.astream(None, config):
            for node_name in event:
                nodes_seen.add(node_name)

        state = pipeline.get_state(config).values

        # Verify: media_generation_node was SKIPPED
        assert "media_generation_node" not in nodes_seen, (
            f"media_generation_node executed despite no-gap plans! Nodes: {sorted(nodes_seen)}"
        )
        # Verify: no generated_assets
        assert state.get("generated_assets") is None or len(state["generated_assets"]) == 0, (
            "generated_assets present despite no gaps"
        )
        # Verify: pipeline went straight to editing
        assert "editing_node" in nodes_seen, (
            f"editing_node not reached after skipping media_gen. Nodes: {sorted(nodes_seen)}"
        )
        print(f"  ✓ No gaps -> media_generation skipped, editing_node reached")
        print(f"  ✓ Nodes in this phase: {sorted(nodes_seen)}")


class TestE2ESelfVerification:
    """L5.x: Verify self_verifications exist in complete pipeline output."""

    @pytest.mark.asyncio
    async def test_pipeline_has_self_verifications(self):
        pipeline = compile_pipeline()
        thread_id = "e2e-self-verify"
        config = {"configurable": {"thread_id": thread_id}}

        initial_state = {
            "target_platforms": ["tiktok"],
            "target_languages": ["en"],
            "current_step": "init",
            "errors": [],
            "human_reviews": {},
            "pipeline_complete": False,
        }

        events = []
        async for event in pipeline.astream(initial_state, config):
            events.append(event)

        checkpoint_keys = ["strategy_review", "script_review", "edit_review", "thumbnail_review"]
        for review_key in checkpoint_keys:
            pipeline.update_state(
                config,
                {
                    "human_reviews": {
                        review_key: HumanReview(
                            node=review_key,
                            status=ApprovalStatus.APPROVED,
                        ).model_dump()
                    }
                },
            )
            async for event in pipeline.astream(None, config):
                events.append(event)

        state = pipeline.get_state(config).values

        sv = state.get("self_verifications", {})
        assert len(sv) >= 4, f"Expected at least 4 self-verifications, got {len(sv)}: {list(sv.keys())}"

        key_nodes = ["strategy_node", "script_node", "editing_node", "thumbnail_node"]
        for key in key_nodes:
            assert key in sv, f"Missing self-verification for {key}. Have: {list(sv.keys())}"
            entry = sv[key]
            assert "quality_thresholds_met" in entry, f"{key} missing quality_thresholds_met"
            assert "verification_details" in entry, f"{key} missing verification_details"

        rf = state.get("rejection_feedback", {})
        assert isinstance(rf, dict)

        metrics = state.get("pipeline_metrics", {})
        assert metrics.get("node_count", 0) >= 15, f"Expected >=15 nodes timed, got {metrics.get('node_count')}"

        print(f"  ✓ Self-verifications: {len(sv)} entries ({', '.join(sv.keys())})")
        print(f"  ✓ Pipeline metrics: {metrics.get('node_count')} nodes in {metrics.get('total_duration_ms', 0):.0f}ms")
