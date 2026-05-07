"""Test-AB(A): Human Review 4 checkpoint 人工分支 + D10 override + contextvars 隔离回归测试。

覆盖内容(对应 CLAUDE.md A 任务):
- 4 个 checkpoint(strategy/script/edit/thumbnail)的 D10 override 三分支
  approved → 进入下一节点
  rejected → 终止 __end__
  changes_requested → 重跑当前节点
- _set_override / _pop_override 不抛 TypeError(审计 P0-01 声明的 bug 不存在,本测试做回归保护)
- contextvars 隔离:并发 asyncio task 不串线
- _set_override 幂等性:重复 set 同一 key 不累积
- _pop_override 在不存在的 key 上不抛错

Test-AB(B) S1 step-by-step + Gate 候选生成全链路放在 tests/test_s1_gate_full_flow.py。
"""

from __future__ import annotations

import asyncio

import pytest

from src.graph.routing import (
    _HUMAN_REVIEW_OVERRIDE,
    _get_override,
    _pop_override,
    _set_override,
    route_after_editing,
    route_after_script,
    route_after_strategy,
    route_after_thumbnail,
)

# 4 checkpoint × 3 expected routing
# checkpoint key → (route_function, approved_target, changes_target)
ROUTING_MATRIX = {
    "strategy": (route_after_strategy, "script_node", "strategy_node"),
    "script": (route_after_script, "compliance_node", "script_node"),
    "edit": (route_after_editing, "audio_node", "editing_node"),
    "thumbnail": (route_after_thumbnail, "distribution_node", "thumbnail_node"),
}


@pytest.fixture(autouse=True)
def _isolate_override_ctx():
    """每个 test 前清空 override map,防止跨 test 串线。"""
    _HUMAN_REVIEW_OVERRIDE.set({})
    yield
    _HUMAN_REVIEW_OVERRIDE.set({})


# ── D10 override setter/getter/pop helpers — 审计 P0-01 回归保护 ──

class TestD10HelpersDoNotRaise:
    """审计声称 _set_override / _pop_override 调用 _get_override 抛 TypeError,
    实际代码 routing.py:39-50 直接读 _HUMAN_REVIEW_OVERRIDE.get(),无此 bug。
    本测试是回归保护,防止未来重构再引入这个 bug。
    """

    def test_set_override_for_each_checkpoint(self):
        for key in ROUTING_MATRIX:
            _set_override(key, {"node_key": f"{key}_review", "status": "approved"})
            override = _get_override(key)
            assert override is not None
            assert override == {"node_key": f"{key}_review", "status": "approved"}

    def test_pop_override_clears_value(self):
        _set_override("strategy", {"node_key": "strategy_review", "status": "approved"})
        assert _get_override("strategy") is not None
        _pop_override("strategy")
        assert _get_override("strategy") is None

    def test_pop_nonexistent_key_does_not_raise(self):
        # 不在 map 里的 key 直接 pop 应该静默成功
        _pop_override("nonexistent_checkpoint")

    def test_set_override_is_idempotent(self):
        _set_override("strategy", {"node_key": "strategy_review", "status": "approved"})
        _set_override("strategy", {"node_key": "strategy_review", "status": "rejected"})
        # 后写覆盖前写
        override = _get_override("strategy")
        assert override is not None
        assert override["status"] == "rejected"

    def test_set_does_not_leak_across_keys(self):
        _set_override("strategy", {"node_key": "strategy_review", "status": "approved"})
        _set_override("script", {"node_key": "script_review", "status": "rejected"})
        # 两个 key 各自独立
        override_strategy = _get_override("strategy")
        override_script = _get_override("script")
        assert override_strategy is not None
        assert override_script is not None
        assert override_strategy["status"] == "approved"
        assert override_script["status"] == "rejected"


# ── 12 用例:4 checkpoint × 3 status ──

@pytest.mark.parametrize("checkpoint_key", list(ROUTING_MATRIX.keys()))
class TestRoutingThreeBranches:
    """每个 checkpoint 3 个分支:approved / rejected / changes_requested。"""

    def test_approved_routes_to_next_node(self, checkpoint_key):
        route_fn, approved_target, _ = ROUTING_MATRIX[checkpoint_key]
        _set_override(checkpoint_key, {"node_key": f"{checkpoint_key}_review", "status": "approved"})
        result = route_fn({})  # type: ignore[arg-type]
        assert result == approved_target, (
            f"{checkpoint_key} approved 应该路由到 {approved_target},实际 {result}"
        )

    def test_rejected_terminates_pipeline(self, checkpoint_key):
        route_fn, _, _ = ROUTING_MATRIX[checkpoint_key]
        _set_override(checkpoint_key, {"node_key": f"{checkpoint_key}_review", "status": "rejected"})
        result = route_fn({})  # type: ignore[arg-type]
        assert result == "__end__", (
            f"{checkpoint_key} rejected 应该终止管线,实际 {result}"
        )

    def test_changes_requested_loops_back(self, checkpoint_key):
        route_fn, _, changes_target = ROUTING_MATRIX[checkpoint_key]
        _set_override(checkpoint_key, {"node_key": f"{checkpoint_key}_review", "status": "changes_requested"})
        result = route_fn({})  # type: ignore[arg-type]
        assert result == changes_target, (
            f"{checkpoint_key} changes_requested 应该重跑 {changes_target},实际 {result}"
        )


class TestOverrideAutoCleared:
    """审计 routing.py 设计:routing 函数命中 D10 override 后自动 _pop_override,
    避免下次路由继续使用旧值。
    """

    @pytest.mark.parametrize("checkpoint_key,expected_target", [
        ("strategy", "script_node"),
        ("script", "compliance_node"),
        ("edit", "audio_node"),
        ("thumbnail", "distribution_node"),
    ])
    def test_override_consumed_after_routing(self, checkpoint_key, expected_target):
        route_fn = ROUTING_MATRIX[checkpoint_key][0]
        _set_override(checkpoint_key, {"node_key": f"{checkpoint_key}_review", "status": "approved"})
        # 第一次路由消费 override
        first = route_fn({})  # type: ignore[arg-type]
        assert first == expected_target
        # 第二次路由 override 已被消费,fall through 到默认路径
        second = route_fn({})  # type: ignore[arg-type]
        # 没有 audit_reports 也没 human_reviews,走 audit_guard 返回 None,
        # 最终 default fall-through 回当前 node 重跑
        assert second != expected_target, (
            f"{checkpoint_key}:第二次路由应该 fall through(override 已消费),"
            f"不应仍返回 {expected_target}"
        )


# ── contextvars 隔离回归 ──

class TestContextvarsIsolation:
    """contextvars.ContextVar 保证不同 asyncio task 互不串线。
    routing.py:28 的 _HUMAN_REVIEW_OVERRIDE 必须是 ContextVar 而不是 dict。
    """

    @pytest.mark.asyncio
    async def test_concurrent_tasks_do_not_share_override(self):
        results: dict[str, str] = {}

        async def task_a():
            _set_override("strategy", {"node_key": "strategy_review", "status": "approved"})
            await asyncio.sleep(0.01)  # 让 task_b 有机会插入
            override = _get_override("strategy")
            assert override is not None
            results["a"] = override["status"]

        async def task_b():
            await asyncio.sleep(0.005)  # 等 task_a 先 set
            # task_b 不应该看到 task_a 的 override
            override = _get_override("strategy")
            results["b"] = override["status"] if override else "no_override"

        await asyncio.gather(task_a(), task_b())
        assert results["a"] == "approved"
        # 关键断言:task_b 在自己的 ctx 里,看不到 task_a 设的 override
        assert results["b"] == "no_override", (
            f"contextvars 隔离失败 — task_b 看到了 task_a 的 override:{results['b']}"
        )


# ── audit guard 自动决策 (高分自动 approve, 低分自动 reject) ──

class TestAuditAutoDecision:
    """0.60-0.90 区间触发 HITL,> 0.90 自动 approve,< 0.60 自动 reject。
    本测试构造每个区间的 audit_report 验证路由结果。
    """

    @pytest.mark.parametrize("checkpoint_key,expected_target", [
        ("strategy", "script_node"),
        ("script", "compliance_node"),
        ("edit", "audio_node"),
        ("thumbnail", "distribution_node"),
    ])
    def test_high_score_auto_approves(self, checkpoint_key, expected_target):
        route_fn = ROUTING_MATRIX[checkpoint_key][0]
        state = {"audit_reports": {checkpoint_key: {"overall_score": 0.95}}}
        result = route_fn(state)  # type: ignore[arg-type]
        assert result == expected_target, (
            f"{checkpoint_key} score=0.95 应该 auto-approve 到 {expected_target},实际 {result}"
        )

    @pytest.mark.parametrize("checkpoint_key", list(ROUTING_MATRIX.keys()))
    def test_low_score_auto_rejects(self, checkpoint_key):
        route_fn = ROUTING_MATRIX[checkpoint_key][0]
        state = {"audit_reports": {checkpoint_key: {"overall_score": 0.40}}}
        result = route_fn(state)  # type: ignore[arg-type]
        assert result == "__end__", (
            f"{checkpoint_key} score=0.40 应该 auto-reject 终止,实际 {result}"
        )

    @pytest.mark.parametrize("checkpoint_key", list(ROUTING_MATRIX.keys()))
    def test_middle_score_falls_through_to_loop(self, checkpoint_key):
        """0.60-0.90 区间不自动决策,fall through 到 default(回 current node 重跑)。"""
        route_fn, _, current_node = ROUTING_MATRIX[checkpoint_key]
        state = {"audit_reports": {checkpoint_key: {"overall_score": 0.75}}}
        result = route_fn(state)  # type: ignore[arg-type]
        assert result == current_node, (
            f"{checkpoint_key} score=0.75 中间区间应该回 {current_node} 重跑,实际 {result}"
        )


# ── degraded guard 短路 ──

class TestDegradedGuardShortCircuits:
    """pipeline_degraded=True 时所有 routing 函数立即终止,
    不检查 D10 override / human_reviews / audit。
    """

    @pytest.mark.parametrize("checkpoint_key", list(ROUTING_MATRIX.keys()))
    def test_degraded_terminates_regardless_of_override(self, checkpoint_key):
        route_fn = ROUTING_MATRIX[checkpoint_key][0]
        # 即使设了 D10 approved override,degraded 也应该短路
        _set_override(checkpoint_key, {"node_key": f"{checkpoint_key}_review", "status": "approved"})
        state = {"pipeline_degraded": True}
        result = route_fn(state)  # type: ignore[arg-type]
        assert result == "__end__", (
            f"{checkpoint_key} degraded 必须立即 __end__,实际 {result}"
        )
