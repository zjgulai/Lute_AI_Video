---
name: adr-007-defer-llm-director-planner
description: ADR 007 — continuity 导演层暂不引入 LLM planner，默认保留确定性 director_profile；未来如引入 LLM，只能作为 feature-flagged 增强并通过 schema 校验与 deterministic fallback。
doc_type: adr
module: pipeline
topic: continuity-director
status: accepted
created: 2026-05-27
updated: 2026-05-27
owner: self
source: human+ai
related:
  - file: ../../workflows/2026-05-14-poyo-constrained-optimization-roadmap.md
    relation: updates
  - file: ../../../src/skills/continuity_storyboard_grid.py
    relation: constrains
---

# ADR #007 — Defer LLM Director Planner for Continuity

| | |
|---|---|
| 状态 | Accepted |
| 日期 | 2026-05-27 |
| 决策者 | 工程团队 |
| 影响 | `src/skills/continuity_storyboard_grid.py`, `src/skills/seedance_prompt.py`, `src/pipeline/candidate_scorer.py`, S1-S5 continuity workflow |

## 一、Context

P4 已把 `continuity_storyboard_grid` 从固定模板推进到输入驱动的规则导演层：当前会派生 `director_profile`，并把 `story_arc`、`audience_tension`、`brand_promise`、`platform_pacing`、`creator_cadence` 注入 `visual_identity`、`clip_groups` 和 Seedance prompt。

下一步问题是：是否继续引入 LLM director planner，让 LLM 生成更自由的镜头编排、节奏与转场语义。

当前约束：

- 用户尚未充值 poyo.ai tokens，不能执行真实视频生成 smoke。
- continuity 当前本地组合回归已通过，覆盖 `continuity_storyboard_grid`、`candidate_scorer`、`S1` continuity 和 `S3/S4/S5` hermetic E2E。
- `candidate_scorer` 与 audit 当前只要求结构化 `scene_beat`、`beat_summary`、`transition_intent` 完整，并不验证 LLM 生成内容的稳定性。
- S1-S5 的 continuity 链路属于热路径，随机 LLM 输出会增加可测性、成本和非确定性风险。

## 二、Decision

**不在当前阶段引入默认 LLM director planner。**

默认 continuity director 继续使用确定性 `director_profile`。如果后续要引入 LLM planner，只能作为可选增强，并必须满足以下边界：

1. 通过 feature flag 开启，例如 `CONTINUITY_DIRECTOR_PLANNER=llm`，默认仍为 `deterministic`。
2. LLM 输出只允许写入结构化 planner payload，不允许直接覆盖下游 `clip_groups` 合同。
3. 输出必须通过 Pydantic / JSON schema 校验，字段至少包括 `scene_beat`、`beat_summary`、`transition_intent`、`brand_promise`、`platform_pacing`。
4. schema 校验失败、超时、空输出或安全规则命中时，必须回退到 deterministic `director_profile`。
5. 所有测试默认使用 deterministic / mocked planner，不依赖外部 token。
6. 只有在真实 poyo 额度可用后，才允许做 production smoke。

## 三、当前实现

当前默认实现：

- [src/skills/continuity_storyboard_grid.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/skills/continuity_storyboard_grid.py) — `_build_director_profile()` 从场景、受众、USP、品牌价值、平台和 creator style 派生导演 profile。
- [src/skills/seedance_prompt.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/skills/seedance_prompt.py) — 消费 `clip_groups` 的 `scene_beat`、`beat_summary`、`transition_intent` 并继续拼入 Seedance prompt。
- [src/pipeline/candidate_scorer.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/pipeline/candidate_scorer.py) — 优先读取结构化导演意图字段，再回退到 prompt 文本。

当前验证：

```bash
.venv/bin/ruff check src/skills/continuity_storyboard_grid.py tests/test_continuity_storyboard_grid.py
.venv/bin/python -m pytest tests/test_continuity_storyboard_grid.py tests/test_candidate_scorer_continuity.py tests/test_s1_continuity_pipeline.py tests/test_s3_e2e.py tests/test_s4_e2e.py tests/test_s5_e2e.py -q
```

结果：`75 passed, 12 deselected`。

## 四、Consequences

**好处：**

- 保持 S1-S5 continuity 热路径确定性，本地可复现。
- 不消耗 poyo tokens，也不引入新的 LLM 成本。
- 不扩大当前 schema、gate、audit 和前端诊断合同。
- 真实生产 smoke 前不会把不可控 LLM 输出引入视频生成链路。

**代价：**

- 导演编排仍是规则层，无法达到真正生成式 director planner 的创造性。
- 针对复杂品牌调性、多角色叙事、平台差异化节奏，当前方案只能做有限语义注入。
- 后续若要升级到 LLM planner，需要单独设计 schema、超时、fallback、评估和非确定性测试。

## 五、Alternatives Considered

| 方案 | 结论 | 理由 |
|---|---|---|
| A. 立即把 `continuity_storyboard_grid` 改成 LLM 生成 | 拒绝 | 会让热路径依赖外部 LLM，当前无真实 poyo token 无法做生产闭环，且非确定性会削弱 hermetic 回归价值。 |
| B. 在规则层继续堆更多场景模板 | 拒绝 | 容易形成模板爆炸，后续维护成本高；P4 的 `director_profile` 已是当前规则层的合理上限。 |
| C. 新增 feature-flagged LLM planner，但默认关闭 | 延后 | 架构可行，但当前没有真实额度和质量样本，先记录为后续实施路径。 |
| D. 保持 deterministic `director_profile` 为默认 | 接受 | 兼顾可测性、成本和当前产品稳定性；能先完成本地可验证闭环。 |

## 六、Rollback Plan

本 ADR 不引入代码路径变更。若未来实施 LLM planner 后出现质量或稳定性问题，回滚方式为：

1. 将 `CONTINUITY_DIRECTOR_PLANNER` 设回 `deterministic`。
2. 保留 deterministic `director_profile` 作为无外部依赖 fallback。
3. 禁止删除 deterministic 路径，除非 LLM planner 已有稳定性测试和生产 smoke 证据。

## 七、相关代码

- [src/skills/continuity_storyboard_grid.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/skills/continuity_storyboard_grid.py)
- [src/skills/seedance_prompt.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/skills/seedance_prompt.py)
- [src/pipeline/candidate_scorer.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/pipeline/candidate_scorer.py)
- [tests/test_continuity_storyboard_grid.py](file:///Users/pray/project/hermes_evo/AI_vedio/tests/test_continuity_storyboard_grid.py)
- [tests/test_candidate_scorer_continuity.py](file:///Users/pray/project/hermes_evo/AI_vedio/tests/test_candidate_scorer_continuity.py)
