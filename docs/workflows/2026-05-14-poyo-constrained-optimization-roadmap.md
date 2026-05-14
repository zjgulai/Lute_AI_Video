---
name: poyo-constrained-optimization-roadmap
description: poyo.ai 约束下的 S1-S5 视频生成 Pipeline 8 周优化排期文档，覆盖模型选型、Gate 阈值差异化、S2 重建、S5 时长解封、合规与降级。当用户需要查询 Sprint 进度、定位某项优化的依赖关系、或更新风险-改善映射时使用。
doc_type: workflow
module: ai-video
topic: pipeline-optimization-roadmap
status: stable
created: 2026-05-14
updated: 2026-05-14
owner: Sisyphus
source: ai
related:
  - file: ./five-scenario-pipeline-risk-assessment-stable-20260513.md
    relation: derived-from
---

# poyo.ai 约束下的 S1-S5 Pipeline 优化排期计划

> **基础诊断**：[【风险评估】五场景Pipeline深度风险评估与改善优化计划](./five-scenario-pipeline-risk-assessment-stable-20260513.md)
> **关键约束（决策 D, 2026-05-13）**：模型选型 **仅限 poyo.ai 模型库**，参照其官网能力矩阵
> **本文目的**：将诊断的 10 个 P0/P1 风险按 poyo 真实能力矩阵进行可执行性校验、重排期、可落地化

---

## 一、关键发现：诊断方案 vs poyo 真实能力（5 项重大偏差）

下表逐条对照诊断推荐与 poyo 2026-05 能力矩阵的真实差距。**这些差距决定排期必须修订**。

| 诊断推荐 | poyo 实际能力（2026-05） | 偏差 | 修订方案 |
|---|---|---|---|
| **Veo 3.1 → S5 单片段 60s** | `veo-3-1` 仅 8s @ 4K（lite/fast/high-quality 三档） | ❌ **诊断失实** | S5 时长解锁改用 **Seedance 2** (15s 多镜头 + 原生音频) + **Kling 3.0 Pro** (15s @ 1080p, 6 镜头) 多片段拼接 |
| **Wan 2.2 自建评估** | `wan-2-7-video` / `wan-2-6` / `wan-2-5` / `wan-2-2-fast` 全部 poyo 直接可用 | ⚠️ **过度工程** | 取消"自建评估"，直接接入 poyo 上的 Wan 2.7 |
| **Runway Gen-4 → S2** | `runway-gen-4-5` 10s @ 1080p 已上 poyo | ✅ 路径可行 | 维持 |
| **Kling 3.0 → S1/S3/S4** | `kling-3-0/standard` 15s @ 720p、`kling-3-0/pro` 15s @ 1080p 已上 poyo | ✅ 路径可行 | 维持 |
| **当前 happy-horse 8s 限制** | 同档替代 `seedance-2` (15s + 多镜头 + 多语言唇形同步) 成本 $0.05–$0.45/s | ✅ 重大升级机会 | **S1/S3/S4 默认模型**从 happy-horse → seedance-2，成本可控 |

**核心修订**：诊断的 6 大「最高优先级行动」中，**第 1 条（Veo 3.1 60s）需要重写为多片段拼接策略**，第 6 条（Wan 自建）转为 poyo 接入，其他维持。

---

## 二、当前代码现状（2026-05-14 已落地）

| 模块 | 文件 | 当前模型 | 升级潜力 |
|---|---|---|---|
| `PoyoClient` | [src/tools/poyo_client.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/tools/poyo_client.py) | 通用提交+轮询，model 参数运行时传入 | ✅ 已支持任意 poyo 模型 ID |
| `SeedanceClient` | [src/tools/seedance_client.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/tools/seedance_client.py) | hardcoded `seedance-2.0`；走 poyo 代理时使用 `POYO_VIDEO_MODEL` | 🟡 需要扩展为按场景选模型 |
| `GPTImageClient` | [src/tools/gpt_image_client.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/tools/gpt_image_client.py) | hardcoded `gpt-image-2` | 🟡 可升级 `nano-banana-pro` (4K 同价) 或 `flux-2`/`seedream-5-0-lite` |
| `POYO_VIDEO_MODEL` | [src/config.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/config.py) | 默认 `happy-horse` (8s) | 🔴 立即可改为 `seedance-2` 或 `kling-3-0/standard` |
| `poyo_safety` | [src/tools/poyo_safety.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/tools/poyo_safety.py) | 11+ 母婴术语替换 | ✅ 已稳定 |
| `candidate_scorer` 婴儿安全维度 | [src/pipeline/candidate_scorer.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/pipeline/candidate_scorer.py) | 已接通（2026-05-14 修复） | ✅ 新增维度 |
| `_validate_s5_scene_id` | [src/routers/scenario.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/routers/scenario.py) | nursery 已边界拦截 | ✅ 决策 E 已落地 |

**结论**：基础设施层已具备多模型路由前提（`PoyoClient.submit(model, ...)` 接口），缺的是 `ModelRouter` 调度层 + 按场景的模型映射表。

---

## 三、模型选型矩阵（poyo 约束版，落地版本）

修订诊断 §3.1 的选型矩阵，全部基于 poyo.ai 2026-05 真实在线模型：

| 场景 | 首选 | 备选 | 降级 | 时长能力 | 单条成本 |
|---|---|---|---|---|---|
| **S1 商品直拍** | `seedance-2` (15s + 多参考图) | `kling-3-0/pro` (15s + 多镜头) | `wan-2-7-video` | 15s × 4-6 段 = 60-90s | $0.75–$6.75/15s |
| **S2 品牌宣传** | `kling-3-0/pro` (1080p + 角色一致性 3 人) | `runway-gen-4-5` (10s @ 1080p) | `wan-2-7-video` | 15s × 4 段 = 60s | $2.93–$3.68/15s |
| **S3 网红二创** | `kling-3-0/standard` (角色一致性) | `seedance-2` | `wan-2-6` | 15s × 2 段 = 30s | $2.03–$2.93/15s |
| **S4 直播拍摄** | `seedance-2-fast` (快速迭代) | `kling-2-5-turbo-pro` (turbo) | `wan-2-2-fast` (budget) | 10-15s × 6 段 | $0.45–$2.10/15s |
| **S5 品牌VLOG** | `seedance-2` (15s + 原生音频 + 多语言唇形) | `kling-3-0/pro` (6 shot 多镜头叙事) | `wan-2-7-video` (15s) | **15s × 6 段 = 90s** | $0.75–$6.75/15s |

**关键变更**：
- `happy-horse` (8s) 全场景退役，仅作为 `wan-animate` 等专用工具的兼容入口
- S5 不再卡 15s 死锁——通过 `seedance-2` 的多镜头 + 多片段拼接实现 30/45/60/90s
- S2 真正与 S1 区分：S1 用 `seedance-2`（产品质感），S2 用 `kling-3-0/pro`（角色一致性 + 情绪叙事）

---

## 四、Gate 阈值差异化（决策 F 落地）

诊断决策 F 要求按模型差异化阈值。基于上表，最终阈值表：

| 模型 | min_threshold | 适用场景 | 理由 |
|---|---|---|---|
| `seedance-2` / `seedance-2-fast` | **0.65** | S1/S5 主力 | ByteDance 高质量基线，要求严格 |
| `kling-3-0/*` | **0.60** | S1/S2/S3 角色场 | 多镜头叙事容忍度略高 |
| `runway-gen-4-5` | **0.62** | S2 品牌宣传 | 介于 Seedance 与 Kling 之间 |
| `wan-2-7-video` / `wan-2-6` | **0.55** | 降级 / 备选 | 容忍度更高，避免降级路径全员阻塞 |
| `wan-2-2-fast` | **0.50** | 极限降级 | budget 路径，质量底线最低 |
| `veo-3-1` | **0.58** | 短片 hero shot（8s 内） | 4K 高质量，但仅短场景 |
| `gpt-image-2` / `nano-banana-pro` | **0.65** | 关键帧 / 缩略图 | 图像质量门槛 |

实现位置：新建 `src/pipeline/model_thresholds.py`，gate_manager 读取 `model_id → threshold` 而非全局硬编码。

---

## 五、修订后排期（4 sprint × 2 周 = 8 周完整路线图）

诊断的 P0/P1/P2 时间盒按 poyo 实际能力 + 已落地状态重新排期。

### Sprint 0（本周末前，3 天） — 零风险快赢

| ID | 行动 | 改动量 | 依赖 | 验收 |
|---|---|---|---|---|
| **S0-1** | 默认 `POYO_VIDEO_MODEL` 从 `happy-horse` 改为 `seedance-2` | 单行 env + 文档 | 无 | `.env.prod` 更新 + 一次 S1 完整 run 验证产出 15s |
| **S0-2** | 修复诊断 §C 决策 D 的 4 个 draft 文档缺失（仅作存根） | 4 个空 frontmatter md | 无 | 文件存在以保证文档链接不悬空 |
| **S0-3** | 新增 `model_thresholds.py` + `gate_manager.score_candidate` 读取 model-aware threshold | ~80 行 | 无 | 7 个模型 × 7 个阈值单测 |
| **S0-4** | 修复 `poyo_constrained_model_selection_draft` 落地为正式文档（`docs/architecture/poyo-model-matrix-stable.md`） | 1 文档 | 本文 | 文档加入 frontmatter + 链接到本路线图 |

**Sprint 0 价值**：把 happy-horse 退役 + 阈值差异化 + 诊断悬空文档 3 件事一次性清理，无重构、无新依赖、无 schema 变更。

### Sprint 1（Week 1-2） — 模型路由层 + S5 时长解封

| ID | 行动 | 改动量 | 依赖 | 验收 |
|---|---|---|---|---|
| **P1-1** | 建立 `src/pipeline/model_router.py` （场景 → 首选/备选/降级 chain） | ~200 行 + 单测 | S0-3 | 5 场景路由表正确返回 + 模型不可用降级测试 |
| **P1-2** | `SeedanceClient` 接受 `model` 参数（非 hardcoded `seedance-2.0`），通过路由层注入 | ~30 行 | P1-1 | S1/S2/S3 单场景指定模型 e2e |
| **P1-3** | 新增 `VideoContinuityManager` skill：跨片段 last_frame 锚定 | ~150 行 + 单测 | 无 | 双片段连接的视觉连续性回归测试 |
| **P1-4** | S5 改造：`seedance_clips` 步骤生成 N 段 15s clip（duration 30/60/90 → N=2/4/6），自动传入 last_frame | ~80 行 | P1-3 | S5 完整 60s 视频产出 + Seedance 2 多片段拼接 |
| **P1-5** | `routers/scenario.py` 决策 E 抽象化扩展：补全 `S5 抽象化视觉规范` 注入 prompt | ~50 行 | 已落地 (5/14) | S5 prompt 中始终包含「禁止可识别儿童面部」注入 |
| **P1-6** | Gate 评分 `min_threshold` 与 model 联动（S0-3 上层封装） | ~40 行 | S0-3 | 4-Gate 评分门槛按模型动态调整 |
| **P1-7** | `test_model_router.py`、`test_video_continuity.py` 完整单测 + S5 60s e2e | ~300 行测试 | P1-1, P1-3 | CI 通过；coverage ≥ 85% on new code |

**Sprint 1 价值**：诊断 R-S5-DURA / R-VENDOR-LOCK / R-S4-CONT 三个 P0/P1 一并打掉。S5 时长死锁解封，模型路由层落地，**不需要 Veo 3.1，不需要 Wan 自建**。

### Sprint 2（Week 3-4） — S2 决策落地 + Gate 视觉评分

诊断决策 A 已选「重建独立管线」。按本路线图能力矩阵，S2 与 S1 的差异从「文本驱动 vs 配置变体」升级为「角色一致性 + 情绪叙事 vs 产品聚焦」。

| ID | 行动 | 改动量 | 依赖 | 验收 |
|---|---|---|---|---|
| **P2-1** | 新建 `src/pipeline/s2_brand_pipeline_v2.py`，独立 strategy/script/storyboard，使用 Kling 3.0 Pro | ~600 行 + e2e 测试 | P1-1, P1-2 | S2 独立管线全步骤；strategy 读取 brand_guidelines |
| **P2-2** | 删除 60 行 deprecated `s2_brand_pipeline.py` wrapper（保留旧文件名为 v2 alias） | -60 / +5 行 | P2-1 | `/scenario/s2` 路由指向新管线；旧调用兼容 |
| **P2-3** | `test_s2_e2e.py` 创建：覆盖 S2 独立 strategy + brand-mode 合规 + 极端输入（诊断 P0-3） | ~250 行 | P2-1 | CI 通过 |
| **P2-4** | Gate 视觉评分升级：keyframe 评分用 `gpt-4o` vision API 实际分析图像（替代 prompt 关键词） | ~150 行 + 单测 | 无 | keyframe 评分接入实际图像 |
| **P2-5** | `candidate_scorer` 5 维权重场景化（诊断 §8.2 矩阵）：S1/S2/S3/S4/S5 各自 6 维专属层 | ~200 行 + 大量单测 | 无 | 5 场景下评分权重不同；breakdown keys 按场景列出 |

**Sprint 2 价值**：诊断 R-S2-ARCH / R-TEST-S2 / R-GATE-SCORE / CQ-1/CQ-2 一并解决。

### Sprint 3（Week 5-6） — 合规 + L2 降级 + 成本

| ID | 行动 | 改动量 | 依赖 | 验收 |
|---|---|---|---|---|
| **P3-1** | EU AI Act C2PA 元数据注入：assemble_final 后嵌入 C2PA manifest | ~120 行 + ffmpeg 集成 | 无 | 输出 mp4 通过 C2PA verify 工具 |
| **P3-2** | 医疗禁用词库扩展（200+词汇）+ Gate 1 强制拦截 | ~600 行词库 + 50 行集成 | 无 | 测试用例覆盖治疗/预防/改善/医疗级等高危词 |
| **P3-3** | L2 跨步骤降级：assemble 失败 → 返回 partial artifacts + degraded_reason | ~150 行 + state schema +1 | 无 | 模拟 assemble 失败，e2e 仍能返回所有上游 artifact |
| **P3-4** | Expert 模式 budget 上限：Gate 3 worst-case 18 次调用拦截到 $5/条 | ~80 行 + 配置 | 无 | 超预算自动降级到 standard 模式 |
| **P3-5** | 状态 schema 版本化（MINOR+1）+ 契约测试 | ~50 行 + 200 行测试 | 无 | schema 不向后破坏现网 thread |
| **P3-6** | S3 版权指纹预审接入（诊断 COMP-CRIT-1） | ~200 行 + 第三方指纹 API | 外部 API 选型 | remix 前自动指纹比对 |

### Sprint 4（Week 7-8） — 测试覆盖 + 平台多规格 + 数据闭环

| ID | 行动 | 改动量 | 依赖 | 验收 |
|---|---|---|---|---|
| **P4-1** | Gate 2/3/4 完整 E2E mock 测试 | ~400 行 | 无 | CI 中 4-Gate 全路径 |
| **P4-2** | 多平台多规格输出（9:16/1:1/16:9 自动适配）：assemble_final 阶段渲染 3 规格 | ~150 行 + Remotion 改造 | 无 | 1 个 source → 3 个 mp4 |
| **P4-3** | AI 非确定性测试框架（`llm_stability` / `media_stability` 标记） | ~200 行 + pytest 配置 | 无 | 5 次同 prompt 字段稳定性回归 |
| **P4-4** | `metrics_repository` PG → 完整数据闭环（诊断 P2-9） | ~300 行 + 前端 dashboard | 已部分落地 | 视频投放数据回流 P8 |
| **P4-5** | S3 链式容错测试 + S4 footage 降级 + S5 stub 检测前置 | ~250 行 | P3-3 | CI 全场景降级路径绿 |

---

## 六、与诊断 §10.4 风险-改善映射的差异

| 诊断风险 ID | 诊断改进 ID | 本路线图对应 ID | 状态变化 |
|---|---|---|---|
| R-S2-ARCH | I-S2-REBUILD / P0-1 | **P2-1, P2-2** | 时间盒 2-4 周 → 2 周（路由层先就位） |
| R-S5-DURA | I-S5-VEO / P1-2 | **P1-3, P1-4** | **不再依赖 Veo 3.1**，改用 Seedance 2 + 续帧 |
| R-GATE-SCORE | I-TEST-SCORER / P0-2,4 | S0-3 + **P2-4, P2-5** | 2 阶段：阈值差异化 (S0) + 视觉评分 (P2) |
| R-TEST-S2 | P0-3 | **P2-3** | 与 P2-1 强绑定，不能并行 |
| R-TEST-GATE | I-TEST-GATE / P1-6 | **P4-1** | 后置到 Sprint 4，S2 重建后才有完整路径可测 |
| R-TEST-SCORER | I-TEST-SCORER / P0-4 | 已部分落地（baby_safety + scene_id） + **P2-5** | 已交付一部分 |
| R-VENDOR-LOCK | I-MODEL-RT / P1-1 | **P1-1, P1-2** | poyo 内部多模型 = 解锁 |
| R-S4-CONT | I-S4-KEYF / P1-3,4 | **P1-3, P1-4**（S4 复用 VideoContinuityManager） | 时间盒不变 |
| R-DEGRADE-L2 | P2-4 | **P3-3** | 时间盒不变 |
| R-COST-EXP | P1-8 | **P3-4** | 时间盒延后 1 sprint，先建路由再控成本 |

---

## 七、立即行动（本周内 — Sprint 0 详单）

按改动量排序，今晚~3 天内完全可落地：

1. **S0-1（30 分钟）**: 修改 [`deploy/lighthouse/.env.prod`](file:///Users/pray/project/hermes_evo/AI_vedio/deploy/lighthouse/.env.prod) 把 `POYO_VIDEO_MODEL=happy-horse` 改为 `seedance-2`。需要先在测试环境跑 1 次 S1 完整 e2e 验证。
2. **S0-3（2 小时）**: 新建 [`src/pipeline/model_thresholds.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/pipeline/model_thresholds.py)（不存在），定义 `MODEL_THRESHOLDS` dict + `get_threshold(model_id) -> float`，gate_manager.score_candidate 调用前查询。单测 `tests/test_model_thresholds.py` 7 case。
3. **S0-2（10 分钟）**: 4 个诊断引用的 draft 文档（`drafts/architecture/s2-brand-campaign-pipeline-design-draft-20260513.md` 等）补存根，避免后续日志告警。
4. **S0-4（1 小时）**: 整理本路线图为 `docs/architecture/poyo-model-matrix-stable.md`（永久版），包含模型 ID + 阈值 + 适用场景的速查表。

---

## 八、决策需用户确认

1. **Sprint 0 是否立即执行？** S0-1（POYO_VIDEO_MODEL=seedance-2）会改变所有走 poyo 路径的视频生成默认行为，建议先在测试环境跑 1 条 S1 验证质量再全量切换。
2. **Sprint 2 中 S2 是否真的重建？** 决策 A 选「重建独立管线」，本路线图按重建排期。如果回到「降级为 S1 配置变体」，Sprint 2 工作量减半。
3. **C2PA 是否在 Sprint 3 必须落地？** EU AI Act 8/2 生效，目前在 5/14，按 Sprint 3 (Week 5-6) 完工 ≈ 6 月底，留 1 个月缓冲。如果合规团队要求更早，需要把 P3-1 提前到 Sprint 1。
4. **预算 budget 上限设多少？** 诊断推荐 Expert mode $5/条，本路线图沿用。需用户最终确认。

---

## 九、文档关联

- 风险评估源文档: [【风险评估】五场景Pipeline深度风险评估与改善优化计划](./five-scenario-pipeline-risk-assessment-stable-20260513.md)
- review 版（含 6 Part 原始证据）: [【风险评估-review】](./five-scenario-pipeline-risk-assessment-review-20260513.md)
- 待写：`docs/architecture/poyo-model-matrix-stable.md`（S0-4 产出）
- 待写：`drafts/architecture/s2-brand-campaign-pipeline-design-draft-20260513.md`（P2-1 前置）

---

*报告版本: v1.0 | 基于 poyo.ai 2026-05 catalog + 当前 git working tree | 下一次更新: Sprint 0 完工后*
