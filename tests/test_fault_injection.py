"""Fault injection tests — verify pipeline degradation path under external API failures.

Covers (CLAUDE.md G task):
- Mock POYO/DeepSeek failure triggers pipeline_degraded=True
- error_collector captures structured error
- /telemetry/errors endpoint returns the error
- StepRunner halts subsequent steps
- PipelineMetrics records failure
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.pipeline.state_manager import PipelineStateManager
from src.pipeline.step_runner import StepRunner
from src.telemetry import error_collector, pipeline_metrics


@pytest.fixture(autouse=True)
def _clear_error_collector():
    """Reset error collector before each test."""
    error_collector._errors.clear()
    pipeline_metrics._step_metrics.clear()
    pipeline_metrics._pipeline_metrics.clear()
    yield
    error_collector._errors.clear()
    pipeline_metrics._step_metrics.clear()
    pipeline_metrics._pipeline_metrics.clear()


class TestStepRunnerDegradedPath:
    """Verify StepRunner._execute_step sets pipeline_degraded on exception."""

    @pytest.mark.asyncio
    async def test_run_step_exception_sets_degraded(self):
        """When pipeline.run_step raises, state.pipeline_degraded becomes True."""
        runner = StepRunner(PipelineStateManager())
        label = await runner.init_state(
            config={"product_catalog": {"products": [{"name": "Test"}]}},
            mode="auto",
            scenario="s1",
        )
        state = await runner.state_manager.load(label)

        with patch(
            "src.pipeline.s1_product_pipeline.S1ProductDirectPipeline.run_step",
            new_callable=AsyncMock,
            side_effect=RuntimeError("POYO API 503"),
        ):
            result = await runner._execute_step(state, "strategy", force=True)

        assert result["pipeline_degraded"] is True
        assert result["degraded_reason"] == "strategy"
        assert any("POYO API 503" in e for e in result.get("errors", []))
        assert result["steps"]["strategy"]["status"] == "error"

    @pytest.mark.asyncio
    async def test_degraded_halts_subsequent_steps(self):
        """Once degraded, run() stops executing further steps."""
        runner = StepRunner(PipelineStateManager())
        label = await runner.init_state(
            config={"product_catalog": {"products": [{"name": "Test"}]}},
            mode="auto",
            scenario="s1",
        )
        state = await runner.state_manager.load(label)

        call_count = 0

        async def fail_once(step_name: str, state: dict):
            nonlocal call_count
            call_count += 1
            if step_name == "strategy":
                raise RuntimeError("DeepSeek timeout")
            return {"mock": step_name}

        with patch(
            "src.pipeline.s1_product_pipeline.S1ProductDirectPipeline.run_step",
            new_callable=AsyncMock,
            side_effect=fail_once,
        ):
            result = await runner.resume(label)

        # strategy fails → pipeline_degraded=True → subsequent steps halted
        assert result.get("pipeline_degraded") is True
        assert call_count == 1, f"Expected 1 call (strategy only), got {call_count}"
        assert result["steps"]["strategy"]["status"] == "error"

    @pytest.mark.asyncio
    async def test_error_collector_receives_structured_error(self):
        """ErrorCollector captures the error with label, step, trace_id."""
        runner = StepRunner(PipelineStateManager())
        label = await runner.init_state(
            config={"product_catalog": {"products": [{"name": "Test"}]}},
            mode="auto",
            scenario="s1",
        )
        state = await runner.state_manager.load(label)
        trace_id = state["trace_id"]

        with patch(
            "src.pipeline.s1_product_pipeline.S1ProductDirectPipeline.run_step",
            new_callable=AsyncMock,
            side_effect=ConnectionError("Seedance refused"),
        ):
            await runner._execute_step(state, "keyframe_images", force=True)

        errors = error_collector.get_errors(label=label)
        assert len(errors) == 1
        err = errors[0]
        assert err["step"] == "keyframe_images"
        assert err["trace_id"] == trace_id
        assert "Seedance refused" in err["error"]
        assert err["label"] == label

    @pytest.mark.asyncio
    async def test_structured_errors_populated(self):
        """state.structured_errors contains PipelineError dict from classify_error."""
        runner = StepRunner(PipelineStateManager())
        label = await runner.init_state(
            config={"product_catalog": {"products": [{"name": "Test"}]}},
            mode="auto",
            scenario="s1",
        )
        state = await runner.state_manager.load(label)

        with patch(
            "src.pipeline.s1_product_pipeline.S1ProductDirectPipeline.run_step",
            new_callable=AsyncMock,
            side_effect=TimeoutError("LLM call timed out after 60s"),
        ):
            result = await runner._execute_step(state, "scripts", force=True)

        structured = result.get("structured_errors", [])
        assert len(structured) == 1
        se = structured[0]
        assert "code" in se
        assert "message" in se
        assert "recoverable" in se
        assert se["recoverable"] is True  # timeout is recoverable

    @pytest.mark.asyncio
    async def test_pipeline_metrics_records_failure(self):
        """PipelineMetrics records the failed step with success=False."""
        runner = StepRunner(PipelineStateManager())
        label = await runner.init_state(
            config={"product_catalog": {"products": [{"name": "Test"}]}},
            mode="auto",
            scenario="s1",
        )
        state = await runner.state_manager.load(label)

        with patch(
            "src.pipeline.s1_product_pipeline.S1ProductDirectPipeline.run_step",
            new_callable=AsyncMock,
            side_effect=ValueError("bad input"),
        ):
            await runner._execute_step(state, "storyboards", force=True)

        step_metrics = pipeline_metrics._step_metrics.get(label, [])
        assert len(step_metrics) == 1
        assert step_metrics[0].step_name == "storyboards"
        assert step_metrics[0].success is False


class TestTelemetryEndpoint:
    """Verify /telemetry/errors returns collected errors."""

    @pytest.mark.asyncio
    async def test_telemetry_errors_endpoint(self):
        """POST a failing scenario then GET /telemetry/errors sees the error."""
        try:
            from httpx import ASGITransport, AsyncClient

            from src.api import app
            from src.routers._deps import verify_api_key
        except ImportError:
            pytest.skip("fastapi not installed")

        app.dependency_overrides[verify_api_key] = lambda: True
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # Seed an error
                error_collector.collect(
                    label="fault_test_001",
                    trace_id="abc123",
                    step="media_generation",
                    error="POYO rate limit exceeded",
                    context={"scenario": "s1", "tenant_id": "test"},
                )

                resp = await client.get("/telemetry/errors?label=fault_test_001")
                assert resp.status_code == 200
                data = resp.json()
                errors = data.get("errors", [])
                assert len(errors) == 1
                assert errors[0]["step"] == "media_generation"
                assert "POYO rate limit exceeded" in errors[0]["error"]
        finally:
            app.dependency_overrides.pop(verify_api_key, None)


class TestDegradedGuardInRouting:
    """Verify routing functions terminate to __end__ when pipeline_degraded is set."""

    @pytest.mark.parametrize("route_fn_name", [
        "route_after_strategy",
        "route_after_script",
        "route_after_editing",
        "route_after_thumbnail",
    ])
    def test_all_routes_terminate_on_degraded(self, route_fn_name):
        from src.graph.routing import (
            route_after_editing,
            route_after_script,
            route_after_strategy,
            route_after_thumbnail,
        )
        route_map = {
            "route_after_strategy": route_after_strategy,
            "route_after_script": route_after_script,
            "route_after_editing": route_after_editing,
            "route_after_thumbnail": route_after_thumbnail,
        }
        route_fn = route_map[route_fn_name]
        state = {"pipeline_degraded": True}
        result = route_fn(state)
        assert result == "__end__", (
            f"{route_fn_name} should return __end__ when degraded, got {result}"
        )
