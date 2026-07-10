---
name: quality-score-feedback-loop-2026-05-15
description: 设计与实现记录 — pipeline 上游 quality_score 驱动下游自动 regenerate。keyframe pilot 已实现；Seedance 与 Remotion consumer 仍在 pilot 范围外。
doc_type: design
module: ai-video
topic: quality-feedback-loop
status: stable
created: 2026-05-15
updated: 2026-07-10
owner: Sisyphus
source: ai
related:
  - file: ../../.kiro/plan/UNIFIED-ROADMAP-2026-05-15.md
    relation: implements-todo-23
---

# Quality Score Feedback Loop — 设计与实现记录

> **当前状态（2026-07-10）**：keyframe pilot 已实现并由 `tests/test_feedback_gate.py`、`tests/test_quality_score_feedback.py` 覆盖。`seedance_video_generate` 与 `remotion_assemble` consumer 仍在 pilot 范围外；扩展会改变 provider 消耗和重生成语义，需另行产品决策。

## 一、当前现状

### Producers — 已 emit `quality_score`

| Skill | 字段 | 范围 |
|---|---|---|
| [`script_writer.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/skills/script_writer.py) | `script._self_check` | dict, 含 `score: float`, `issues: list` |
| [`seedance_prompt.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/skills/seedance_prompt.py) | `prompt.quality_score` + `data.overall_quality_score` | 0.0-1.0 |
| [`character_identity.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/skills/character_identity.py) | `attributes.face_quality_score` | 0.0-1.0 |
| [`candidate_scorer.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/pipeline/candidate_scorer.py) | `score.overall` + `breakdown` | 0.0-1.0 |

### Consumers — keyframe pilot 已接入

| Downstream skill | 当前 retry 逻辑 | 缺失 |
|---|---|---|
| [`keyframe_images.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/skills/keyframe_images.py) | API failure + feedback gate | 已读取 storyboard `quality_score`；支持 proceed / warn / regenerate / attempts exhausted |
| [`seedance_video_generate.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/skills/seedance_video_generate.py) | API failure + duration verification 重试 | 不读 prompt 的 `quality_score` |
| [`remotion_assemble.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/skills/remotion_assemble.py) | 仅 ffmpeg 失败重试 | 不读 clip 的 `quality_score` |

### 后果

- 上游 LLM 输出 quality 0.4（差），下游照样消耗 POYO 调用生成 keyframe / 视频
- 浪费成本（一次 seedance-2 调用 $0.45-3.00）
- 用户最终拿到低质量产物，没有自动止损

## 二、设计

### 2.1 决策矩阵（per consumer）

```
upstream_score < REGENERATE_THRESHOLD  → 不调用下游，触发上游重生成
upstream_score < WARN_THRESHOLD        → 调用下游，但 attach degraded_reason
upstream_score >= WARN_THRESHOLD       → 正常调用
```

每个 consumer 一组阈值（基于上游 skill 的 score 分布特性）：

| Consumer | upstream skill | REGENERATE_THRESHOLD | WARN_THRESHOLD | 上限尝试 |
|---|---|---|---|---|
| `keyframe_images` | `storyboard` (来自 `seedance_prompt`) | 0.50 | 0.70 | 2 次 regenerate |
| `seedance_video_generate` | `seedance_prompt` | 0.55 | 0.75 | 2 次 |
| `remotion_assemble` | `seedance_clips` (per-clip score) | 0.45 | 0.65 | 1 次 (assemble 是 final, 重试 cost 高) |

**理由**：
- keyframe regenerate cost ~$0.05/张 → 阈值低些
- seedance regenerate cost ~$0.45-3/视频 → 阈值中等
- remotion 不调外部 API，但 chain 上所有依赖都要重新跑 → 只允许 1 次

### 2.2 实现契约

新 module `src/pipeline/quality_gate.py`（不是新组件，是 skill 调用前的 helper）：

```python
from typing import Any, Literal

GateDecision = Literal["proceed", "warn", "regenerate"]


def evaluate_upstream_quality(
    upstream_data: dict[str, Any],
    consumer: str,
    score_path: str = "quality_score",
    *,
    attempt: int = 0,
) -> tuple[GateDecision, float, str]:
    """根据上游 quality_score 决定下游行为。

    Returns:
        (decision, score, reason)
        - decision: 'proceed' / 'warn' / 'regenerate'
        - score: 实际读到的分数（缺失则 1.0 = 跳过 gate）
        - reason: 人类可读决策依据
    """
    thresholds = _CONSUMER_THRESHOLDS[consumer]
    score = _extract_score(upstream_data, score_path)

    if score is None:
        return "proceed", 1.0, f"{consumer}: no upstream score, default proceed"

    if attempt >= thresholds["max_regenerate_attempts"]:
        return "warn", score, f"{consumer}: score={score:.2f} but attempts exhausted, force proceed with warn"

    if score < thresholds["regenerate"]:
        return "regenerate", score, f"{consumer}: score={score:.2f} < {thresholds['regenerate']}, regenerate upstream"
    if score < thresholds["warn"]:
        return "warn", score, f"{consumer}: score={score:.2f} < {thresholds['warn']}, proceed but flag"
    return "proceed", score, f"{consumer}: score={score:.2f} OK"


_CONSUMER_THRESHOLDS = {
    "keyframe_images": {"regenerate": 0.50, "warn": 0.70, "max_regenerate_attempts": 2},
    "seedance_video_generate": {"regenerate": 0.55, "warn": 0.75, "max_regenerate_attempts": 2},
    "remotion_assemble": {"regenerate": 0.45, "warn": 0.65, "max_regenerate_attempts": 1},
}
```

调用方（每个 consumer skill 的入口）：

```python
async def execute(self, params: dict) -> SkillResult:
    upstream = params.get("storyboard") or params.get("scripts", [{}])[0]
    decision, score, reason = evaluate_upstream_quality(
        upstream, "keyframe_images", attempt=params.get("_attempt", 0)
    )
    if decision == "regenerate":
        return SkillResult.regenerate_upstream(
            upstream_skill="seedance_prompt",
            reason=reason,
            score=score,
        )
    if decision == "warn":
        # proceed but mark degraded so partial_artifacts.summarize can flag
        params["_quality_warning"] = reason
    # ... existing logic
```

### 2.3 调用方 wiring

`step_runner.py` 处理 `SkillResult.regenerate_upstream` 信号：

```python
# 简化伪码：
if result.regenerate_upstream:
    state["regenerate_chain"] = state.get("regenerate_chain", []) + [
        {"skill": result.upstream_skill, "reason": result.reason, "score": result.score}
    ]
    # 重新调度上游 skill，attempt 计数 +1
    upstream_step = _step_for_skill(result.upstream_skill)
    state["steps"][upstream_step]["status"] = "pending"
    state["current_step"] = upstream_step
    return state
```

需要 `state.regenerate_chain` 新字段做 audit trail（哪些步骤被自动触发重生成）。

## 三、Pilot 范围（已落地）

已完成 **`keyframe_images` consumer**：

1. `src/pipeline/feedback_gate.py` 提供集中阈值与决策函数。
2. `src/skills/keyframe_images.py` 在 provider-backed keyframe 生成前调用 feedback gate。
3. `src/pipeline/step_runner.py` 处理 `regenerate_upstream` 信号并记录 `regenerate_chain`。
4. `pipeline_states` 持久化 `regenerate_chain`。
5. `tests/test_quality_score_feedback.py` 覆盖：
   - 上游 score 0.85 → consumer proceed normal
   - 上游 score 0.65 → consumer proceed with warn flag
   - 上游 score 0.40 → consumer regenerate, attempt 1
   - 上游 score 0.40, attempt=2 → force proceed with warn (max attempts)

当前实现边界保持 keyframe-only，不从 helper 中已定义的 Seedance/Remotion 阈值外推为对应 consumer 已接入。

## 四、未在 pilot 范围

- **seedance_video_generate**: 跨过 keyframe pilot 稳定后再加
- **remotion_assemble**: 最末端，影响最小，最后做
- **quality_score 标准化**: 上游 3 个 producer score 算法不同 (script `_self_check.score` vs prompt `quality_score`)，pilot 阶段假设它们都是 0-1 normalized；如果证伪需 normalize layer
- **降级到上游再上游**: keyframe 触发 prompt 重生成，prompt 再 fail → 不向 storyboard 再降级，直接 force proceed (避免无限链)

## 五、风险

| 风险 | 缓解 |
|---|---|
| **regenerate cost 失控**: 极端场景 quality 一直差，每次 regenerate 又花 $0.5 | `max_regenerate_attempts` 硬限 + Sprint 3 P3-4 BudgetExceededError 全局 budget guard 兜底 |
| **score 分布偏移**: 如果上游 prompt skill 改算法导致 score 整体偏低，所有 keyframe 都触发 regenerate | 阈值在 `_CONSUMER_THRESHOLDS` 集中配置 + 加监控指标 `regenerate_rate / hour`，> 30% 报警 |
| **circular regenerate**: A 触发 B regenerate, B 触发 A regenerate | `regenerate_chain` 长度上限 5 + 同 skill 不允许出现 2 次 |

## 六、成功标准

pilot 上线 7 天后：
- regenerate_rate 在 5%-25% 之间（< 5% 说明 gate 太松，> 25% 太严）
- 用户主观质量评分（产品端调研）相比 baseline 提升 ≥ 0.5 分
- 总 cost 上升 < 15%（regenerate cost 被避免下游浪费抵消）

如果 regenerate_rate < 5%，下调阈值；> 25% 则上调。

## 七、决策入口

后续决策入口：
- **"复核 quality feedback pilot"** → 运行 `tests/test_feedback_gate.py` 与 `tests/test_quality_score_feedback.py`
- **"调阈值"** → 改 `_CONSUMER_THRESHOLDS` dict 的数字
- **"扩展到 seedance"** → pilot 稳定后追加 seedance_video_generate consumer

## 八、相关文档

- 排期：[2026-05-14-poyo-constrained-optimization-roadmap.md](file:///Users/pray/project/hermes_evo/AI_vedio/docs/workflows/2026-05-14-poyo-constrained-optimization-roadmap.md) (没有显式 P-ID, 是 NEXT-STEPS P2-9)
- 上游 producer 代码索引（前面 §一表格）
- 现有 candidate_scorer.py 的 model-aware threshold（Phase 0 S0-3）— 这是同源思想但作用域不同（gate 评分 vs 下游 regenerate 决策）
