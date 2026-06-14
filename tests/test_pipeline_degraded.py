"""Test-CG: Distribution + 错误降级回归测试。

对应 CLAUDE.md「Known Gaps」C+G 任务。

C(Distribution): connector registry / 错误路径
- get_connector("tiktok") / get_connector("shopify") 返回正确实例
- get_connector("unknown") raise ValueError
- 真实 platform credentials 需要的端到端发布跑 manual e2e,本测试范围内
  只验 mock 路径

G(错误降级):
- ErrorCollector.collect / get_errors / FIFO bounded(100)
- ErrorCollector.get_errors 按 label 过滤
- timed_node decorator 在节点抛异常时 collect + 仍 re-raise
- _degraded_guard 已经在 test_human_review_branches.py 覆盖

降级链路从 timed_node decorator 开始:
  节点抛 → 记 metric / 收集 error / 重抛
  __wrap_node_with_error_handling(在 src/graph/nodes.py)捕获 +
  设 state["pipeline_degraded"] = True →
  routing 函数检查 _degraded_guard 并 short-circuit __end__
"""

from __future__ import annotations

import pytest

from src.connectors.registry import get_connector
from src.telemetry import ErrorCollector

# ── connector registry ──

class TestConnectorRegistry:
    """get_connector 是 platform name → connector instance 的注册表。"""

    def test_tiktok_returns_instance(self):
        c = get_connector("tiktok")
        assert c is not None
        # publish 是 abstract 但实现类必须有
        assert hasattr(c, "publish")
        assert hasattr(c, "get_status")

    def test_shopify_returns_instance(self):
        c = get_connector("shopify")
        assert c is not None
        assert hasattr(c, "publish")
        assert hasattr(c, "get_status")

    def test_unknown_platform_raises(self):
        with pytest.raises(ValueError, match="Unsupported platform"):
            get_connector("amazon")

    def test_unknown_platform_includes_name_in_error(self):
        with pytest.raises(ValueError) as exc_info:
            get_connector("youtube")
        assert "youtube" in str(exc_info.value)


# ── ErrorCollector ──

class TestErrorCollectorBasic:
    def test_collect_stores_all_fields(self):
        ec = ErrorCollector()
        ec.collect(
            label="run-1",
            trace_id="trace-abc",
            step="strategy_node",
            error="LLM timeout",
            context={"provider": "deepseek"},
        )
        errors = ec.get_errors()
        assert len(errors) == 1
        e = errors[0]
        assert e["label"] == "run-1"
        assert e["trace_id"] == "trace-abc"
        assert e["step"] == "strategy_node"
        assert e["error"] == "LLM timeout"
        assert e["context"] == {"provider": "deepseek"}
        assert "timestamp" in e

    def test_get_errors_filters_by_label(self):
        ec = ErrorCollector()
        ec.collect(label="run-A", trace_id="t1", step="s", error="e1", context={})
        ec.collect(label="run-B", trace_id="t2", step="s", error="e2", context={})
        ec.collect(label="run-A", trace_id="t3", step="s", error="e3", context={})

        all_errors = ec.get_errors()
        assert len(all_errors) == 3

        a_errors = ec.get_errors(label="run-A")
        assert len(a_errors) == 2
        assert {e["error"] for e in a_errors} == {"e1", "e3"}

        b_errors = ec.get_errors(label="run-B")
        assert len(b_errors) == 1
        assert b_errors[0]["error"] == "e2"

    def test_get_errors_returns_copy_not_internal_deque(self):
        ec = ErrorCollector()
        ec.collect(label="x", trace_id="t", step="s", error="e", context={})
        errors = ec.get_errors()
        errors.append({"injected": True})  # 改返回值不应影响内部状态
        assert len(ec.get_errors()) == 1

    def test_unknown_label_returns_empty(self):
        ec = ErrorCollector()
        ec.collect(label="real", trace_id="t", step="s", error="e", context={})
        assert ec.get_errors(label="not-there") == []

    def test_context_is_dict_copy(self):
        """ErrorCollector.collect 把 context dict 拷贝一份,
        外部修改原 context 不影响已收集的 error。"""
        ec = ErrorCollector()
        ctx = {"key": "value"}
        ec.collect(label="x", trace_id="t", step="s", error="e", context=ctx)
        ctx["key"] = "MUTATED"
        stored = ec.get_errors()[0]["context"]
        assert stored["key"] == "value", (
            "ErrorCollector 应该 deep-copy context 防止外部 mutation"
        )


class TestErrorCollectorFIFOBounded:
    """deque(maxlen=100) 让最早的错误被自动弹出,内存不会无限增长。"""

    def test_at_capacity_holds_100(self):
        ec = ErrorCollector()
        for i in range(100):
            ec.collect(label="run", trace_id=f"t{i}", step="s", error=f"e{i}", context={})
        assert len(ec.get_errors()) == 100

    def test_over_capacity_evicts_oldest(self):
        ec = ErrorCollector()
        for i in range(150):
            ec.collect(label="run", trace_id=f"t{i}", step="s", error=f"e{i}", context={})

        errors = ec.get_errors()
        assert len(errors) == 100
        # 前 50 个被淘汰,留 e50..e149
        assert errors[0]["error"] == "e50"
        assert errors[-1]["error"] == "e149"

    def test_fifo_order_preserved(self):
        ec = ErrorCollector()
        ec.collect(label="run", trace_id="t1", step="s", error="first", context={})
        ec.collect(label="run", trace_id="t2", step="s", error="second", context={})
        ec.collect(label="run", trace_id="t3", step="s", error="third", context={})

        errors = ec.get_errors()
        assert [e["error"] for e in errors] == ["first", "second", "third"]


# ── timed_node decorator 异常路径 ──

class TestTimedNodeErrorPath:
    """节点抛异常时 timed_node 必须:
      1. 记录失败 metric
      2. 调 error_collector.collect 收集 structured error
      3. 重新抛出原始异常(不静默吞)
    """

    def test_decorator_collects_error_on_exception(self):
        from src.telemetry import error_collector, timed_node

        # 清空 collector 避免被其他 test 污染断言
        error_collector._errors.clear()

        @timed_node
        def failing_node(state):
            raise RuntimeError("simulated LLM failure")

        with pytest.raises(RuntimeError, match="simulated LLM failure"):
            failing_node({"trace_id": "test-trace-1"})

        errors = error_collector.get_errors()
        assert len(errors) >= 1
        last = errors[-1]
        assert last["step"] == "failing_node"
        assert "simulated LLM failure" in last["error"]
        assert last["context"] == {"node": "failing_node"}

    def test_decorator_records_success_metric(self):
        from src.telemetry import timed_node

        @timed_node
        def ok_node(state):
            return {"ok": True}

        result = ok_node({"trace_id": "test-trace-2"})
        assert result["ok"] is True
        assert result["trace_id"] == "test-trace-2"
        assert result["pipeline_metrics"]["node_count"] >= 1
        assert result["pipeline_metrics"]["steps"][-1]["step_name"] == "ok_node"

    def test_re_raises_exception_after_collect(self):
        """timed_node 收集 error 后必须重抛,不能静默。"""
        from src.telemetry import timed_node

        @timed_node
        def explosive(state):
            raise ValueError("specific error type")

        with pytest.raises(ValueError):
            explosive({"trace_id": "t"})


# ── _degraded_guard short-circuit + state propagation ──

class TestDegradedStatePropagation:
    """state["pipeline_degraded"] = True 时,所有 routing 函数应该 __end__。
    _degraded_guard 单一职责测试,routing 函数级覆盖见 test_human_review_branches.py。
    """

    def test_degraded_guard_returns_end_when_true(self):
        from src.graph.routing import _degraded_guard

        assert _degraded_guard({"pipeline_degraded": True}) == "__end__"

    def test_degraded_guard_returns_none_when_false(self):
        from src.graph.routing import _degraded_guard

        assert _degraded_guard({"pipeline_degraded": False}) is None

    def test_degraded_guard_returns_none_when_missing(self):
        from src.graph.routing import _degraded_guard

        assert _degraded_guard({}) is None

    def test_degraded_guard_returns_none_when_truthy_other(self):
        """guard 只对 pipeline_degraded 字段敏感,其他 truthy 值不触发。"""
        from src.graph.routing import _degraded_guard

        assert _degraded_guard({"errors": ["something"]}) is None
        assert _degraded_guard({"current_step": "strategy"}) is None
