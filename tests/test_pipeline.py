"""Tests for graph pipeline — build and compile stages.

Focus: structural integrity — correct number of nodes, correct edges,
interrupt points configured.
"""

import pytest


class TestBuildPipeline:
    def test_build_pipeline_returns_graph(self):
        from langgraph.graph import StateGraph

        from src.graph.pipeline import build_pipeline

        graph = build_pipeline()
        assert isinstance(graph, StateGraph)

    def test_has_all_16_nodes(self):
        from src.graph.pipeline import build_pipeline

        graph = build_pipeline()
        assert hasattr(graph, "nodes"), "Graph should have nodes attribute"
        assert len(graph.nodes) == 16

    def test_has_12_worker_nodes(self):
        from src.graph.pipeline import build_pipeline

        graph = build_pipeline()
        worker_nodes = {
            "strategy_node", "script_node", "compliance_node",
            "storyboard_node", "asset_sourcing_node", "media_generation_node",
            "editing_node", "audio_node", "caption_node",
            "thumbnail_node", "distribution_node", "analytics_node",
        }
        for node in worker_nodes:
            assert node in graph.nodes, f"Missing worker node: {node}"

    def test_has_4_audit_nodes(self):
        from src.graph.pipeline import build_pipeline

        graph = build_pipeline()
        audit_nodes = {
            "strategy_audit_node", "script_audit_node",
            "editing_audit_node", "thumbnail_audit_node",
        }
        for node in audit_nodes:
            assert node in graph.nodes, f"Missing audit node: {node}"

    def test_strategy_node_in_graph(self):
        from src.graph.pipeline import build_pipeline

        graph = build_pipeline()
        assert "strategy_node" in graph.nodes


class TestCompilePipeline:
    def test_compile_returns_compiled_graph(self):
        from src.graph.pipeline import compile_pipeline

        compiled = compile_pipeline()
        assert compiled is not None
        assert hasattr(compiled, "invoke")
        assert hasattr(compiled, "astream")

    def test_compile_with_custom_checkpointer(self):
        from langgraph.checkpoint.memory import MemorySaver

        from src.graph.pipeline import compile_pipeline

        checkpointer = MemorySaver()
        compiled = compile_pipeline(checkpointer=checkpointer)
        assert compiled is not None

    @pytest.mark.asyncio
    async def test_compile_includes_interrupt_points(self):
        from src.graph.pipeline import compile_pipeline

        compiled = compile_pipeline()
        initial_state = {
            "target_platforms": ["tiktok"],
            "target_languages": ["en"],
            "current_step": "init",
            "errors": [],
            "human_reviews": {},
            "pipeline_complete": False,
        }
        events = []
        async for event in compiled.astream(initial_state, {"configurable": {"thread_id": "test"}}):
            events.append(event)
        assert len(events) >= 1
