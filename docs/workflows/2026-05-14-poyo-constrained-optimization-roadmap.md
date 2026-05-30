---
name: poyo-constrained-optimization-roadmap
description: poyo.ai 约束下的 S1-S5 视频生成 Pipeline 8 周优化排期文档，覆盖模型选型、Gate 阈值差异化、S2 重建、S5 时长解封、合规与降级。当用户需要查询 Sprint 进度、定位某项优化的依赖关系、或更新风险-改善映射时使用。
doc_type: workflow
module: ai-video
topic: pipeline-optimization-roadmap
status: stable
created: 2026-05-14
updated: 2026-05-31
owner: Sisyphus
source: ai
related:
  - file: ./five-scenario-pipeline-risk-assessment-stable-20260513.md
    relation: derived-from
---

# poyo.ai 约束下的 S1-S5 Pipeline 优化排期计划

> **历史语境（2026-05-31）**：本文是 2026-05-14 基于 poyo.ai 当时目录做出的约束版路线图，保留为模型选型与风险映射证据。它不再是当前执行计划；当前 TODO 入口是 [`docs/claude/known-gaps-stable.md`](../claude/known-gaps-stable.md)。真实消耗 POYO token 前，必须重新核对 poyo.ai 当前模型目录、价格和内容审核规则。

> **基础诊断**：[【风险评估】五场景Pipeline深度风险评估与改善优化计划](./five-scenario-pipeline-risk-assessment-stable-20260513.md)
> **关键约束（决策 D, 2026-05-13）**：模型选型 **仅限 poyo.ai 模型库**，参照其官网能力矩阵
> **本文目的**：将诊断的 10 个 P0/P1 风险按 poyo 真实能力矩阵进行可执行性校验、重排期、可落地化

---

## 一、关键发现：诊断方案 vs poyo 真实能力（5 项重大偏差）

下表逐条对照诊断推荐与 poyo 2026-05 能力矩阵的真实差距。**这些差距决定排期必须修订**。

| 诊断推荐 | poyo 实际能力（2026-05） | 偏差 | 修订方案 |
|---|---|---|---|
| **Veo 3.1 → S5 单片段 60s** | `veo-3-1` 仅 8s @ 4K（lite/fast/high-quality 三档） | ❌ **诊断失实** | S5 时长解锁改用 **Seedance 2** (15s 多镜头 + 原生音频) + **Kling 3.0 Pro** (15s @ 1080p, 6 镜头) 多片段拼接 |
| **Wan 2.2 自建评估** | `wan2.7-text-to-video` / `wan2.6-text-to-video` / `wan2.5-text-to-video` / `wan2.5-text-to-video` 全部 poyo 直接可用 | ⚠️ **过度工程** | 取消"自建评估"，直接接入 poyo 上的 Wan 2.7 |
| **Runway Gen-4 → S2** | `runway-gen-4.5` 10s @ 1080p 已上 poyo | ✅ 路径可行 | 维持 |
| **Kling 3.0 → S1/S3/S4** | `kling-3.0/standard` 15s @ 720p、`kling-3.0/pro` 15s @ 1080p 已上 poyo | ✅ 路径可行 | 维持 |
| **当前 happy-horse 8s 限制** | 同档替代 `seedance-2` (15s + 多镜头 + 多语言唇形同步) 成本 $0.05–$0.45/s | ✅ 重大升级机会 | **S1/S3/S4 默认模型**从 happy-horse → seedance-2，成本可控 |

**核心修订**：诊断的 6 大「最高优先级行动」中，**第 1 条（Veo 3.1 60s）需要重写为多片段拼接策略**，第 6 条（Wan 自建）转为 poyo 接入，其他维持。

---

## 二、当前代码现状（2026-05-14 已落地）

| 模块 | 文件 | 当前模型 | 升级潜力 |
|---|---|---|---|
| `PoyoClient` | [src/tools/poyo_client.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/tools/poyo_client.py) | 通用提交+轮询，model 参数运行时传入 | ✅ 已支持任意 poyo 模型 ID |
| `SeedanceClient` | [src/tools/seedance_client.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/tools/seedance_client.py) | hardcoded `seedance-2.0`；走 poyo 代理时使用 `POYO_VIDEO_MODEL` | 🟡 需要扩展为按场景选模型 |
| `GPTImageClient` | [src/tools/gpt_image_client.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/tools/gpt_image_client.py) | hardcoded `gpt-image-2` | 🟡 可升级 `nano-banana-pro` (4K 同价) 或 `flux-2`/`seedream-5-0-lite` |
| `POYO_VIDEO_MODEL` | [src/config.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/config.py) | 默认 `happy-horse` (8s) | 🔴 立即可改为 `seedance-2` 或 `kling-3.0/standard` |
| `poyo_safety` | [src/tools/poyo_safety.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/tools/poyo_safety.py) | 11+ 母婴术语替换 | ✅ 已稳定 |
| `candidate_scorer` 婴儿安全维度 | [src/pipeline/candidate_scorer.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/pipeline/candidate_scorer.py) | 已接通（2026-05-14 修复） | ✅ 新增维度 |
| `_validate_s5_scene_id` | [src/routers/scenario.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/routers/scenario.py) | nursery 已边界拦截 | ✅ 决策 E 已落地 |

**结论**：基础设施层已具备多模型路由前提（`PoyoClient.submit(model, ...)` 接口），缺的是 `ModelRouter` 调度层 + 按场景的模型映射表。

---

## 三、模型选型矩阵（poyo 约束版，落地版本）

修订诊断 §3.1 的选型矩阵，全部基于 poyo.ai 2026-05 真实在线模型：

| 场景 | 首选 | 备选 | 降级 | 时长能力 | 单条成本 |
|---|---|---|---|---|---|
| **S1 商品直拍** | `seedance-2` (15s + 多参考图) | `kling-3.0/pro` (15s + 多镜头) | `wan2.7-text-to-video` | 15s × 4-6 段 = 60-90s | $0.75–$6.75/15s |
| **S2 品牌宣传** | `kling-3.0/pro` (1080p + 角色一致性 3 人) | `runway-gen-4.5` (10s @ 1080p) | `wan2.7-text-to-video` | 15s × 4 段 = 60s | $2.93–$3.68/15s |
| **S3 网红二创** | `kling-3.0/standard` (角色一致性) | `seedance-2` | `wan2.6-text-to-video` | 15s × 2 段 = 30s | $2.03–$2.93/15s |
| **S4 直播拍摄** | `seedance-2-fast` (快速迭代) | `kling-2.5-turbo-pro` (turbo) | `wan2.5-text-to-video` (budget) | 10-15s × 6 段 | $0.45–$2.10/15s |
| **S5 品牌VLOG** | `seedance-2` (15s + 原生音频 + 多语言唇形) | `kling-3.0/pro` (6 shot 多镜头叙事) | `wan2.7-text-to-video` (15s) | **15s × 6 段 = 90s** | $0.75–$6.75/15s |

**关键变更**：
- `happy-horse` (8s) 全场景退役，仅作为 `wan-animate` 等专用工具的兼容入口
- S5 不再卡 15s 死锁——通过 `seedance-2` 的多镜头 + 多片段拼接实现 30/45/60/90s
- S2 真正与 S1 区分：S1 用 `seedance-2`（产品质感），S2 用 `kling-3.0/pro`（角色一致性 + 情绪叙事）

---

## 四、Gate 阈值差异化（决策 F 落地）

诊断决策 F 要求按模型差异化阈值。基于上表，最终阈值表：

| 模型 | min_threshold | 适用场景 | 理由 |
|---|---|---|---|
| `seedance-2` / `seedance-2-fast` | **0.65** | S1/S5 主力 | ByteDance 高质量基线，要求严格 |
| `kling-3.0/*` | **0.60** | S1/S2/S3 角色场 | 多镜头叙事容忍度略高 |
| `runway-gen-4.5` | **0.62** | S2 品牌宣传 | 介于 Seedance 与 Kling 之间 |
| `wan2.7-text-to-video` / `wan2.6-text-to-video` | **0.55** | 降级 / 备选 | 容忍度更高，避免降级路径全员阻塞 |
| `wan2.5-text-to-video` | **0.50** | 极限降级 | budget 路径，质量底线最低 |
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
| **P2-2** | 冻结 deprecated `s2_brand_pipeline.py` shim：旧文件名仅保留 warning-only v2 alias，删除需外部迁移窗口 + 单独确认 | +契约测试 | P2-1 | `/scenario/s2` 路由直连新管线；旧调用收到 DeprecationWarning 且继续兼容 |
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

## 七、历史立即行动（Sprint 0 详单，已失效为当前计划）

> 下面条目保留为 2026-05-14 执行背景。当前执行顺序以 [`docs/claude/known-gaps-stable.md`](../claude/known-gaps-stable.md) 为准。

按改动量排序，今晚~3 天内完全可落地：

1. **S0-1（30 分钟）**: 修改 [`deploy/lighthouse/.env.prod`](file:///Users/pray/project/hermes_evo/AI_vedio/deploy/lighthouse/.env.prod) 把 `POYO_VIDEO_MODEL=happy-horse` 改为 `seedance-2`。需要先在测试环境跑 1 次 S1 完整 e2e 验证。
2. **S0-3（2 小时）**: 新建 [`src/pipeline/model_thresholds.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/pipeline/model_thresholds.py)（不存在），定义 `MODEL_THRESHOLDS` dict + `get_threshold(model_id) -> float`，gate_manager.score_candidate 调用前查询。单测 `tests/test_model_thresholds.py` 7 case。
3. **S0-2（10 分钟）**: 4 个诊断引用的 draft 文档（`drafts/architecture/s2-brand-campaign-pipeline-design-draft-20260513.md` 等）补存根，避免后续日志告警。
4. **S0-4（1 小时）**: 整理本路线图为 `docs/architecture/poyo-model-matrix-stable.md`（永久版），包含模型 ID + 阈值 + 适用场景的速查表。

---

## 八、历史决策项（保留背景，不作为当前阻塞）

> 下列决策项已经在后续版本、ADR、runbook 或本地技术债计划中被部分取代。需要重新决策时，以新的 ADR 或 [`known-gaps-stable.md`](../claude/known-gaps-stable.md) 新增条目为准。

1. **Sprint 0 是否立即执行？** S0-1（POYO_VIDEO_MODEL=seedance-2）会改变所有走 poyo 路径的视频生成默认行为，建议先在测试环境跑 1 条 S1 验证质量再全量切换。
2. **Sprint 2 中 S2 是否真的重建？** 决策 A 选「重建独立管线」，本路线图按重建排期。如果回到「降级为 S1 配置变体」，Sprint 2 工作量减半。
3. **C2PA 是否在 Sprint 3 必须落地？** EU AI Act 8/2 生效，目前在 5/14，按 Sprint 3 (Week 5-6) 完工 ≈ 6 月底，留 1 个月缓冲。如果合规团队要求更早，需要把 P3-1 提前到 Sprint 1。
4. **预算 budget 上限设多少？** 诊断推荐 Expert mode $5/条，本路线图沿用。需用户最终确认。

---

## 九、历史文档关联

- 风险评估源文档: [【风险评估】五场景Pipeline深度风险评估与改善优化计划](./five-scenario-pipeline-risk-assessment-stable-20260513.md)
- review 版（含 6 Part 原始证据）: [【风险评估-review】](./five-scenario-pipeline-risk-assessment-review-20260513.md)
- 历史 S0-4 产出：`docs/architecture/poyo-model-matrix-stable.md`
- 历史 P2-1 前置草稿：`drafts/architecture/s2-brand-campaign-pipeline-design-draft-20260513.md`

---

## 十、2026-05-25 历史执行状态与下一步计划

### 当前状态

- 已完成阶段 1：scenario step order 收敛，`S4/S5` gate 不再跳过 continuity
- 已完成阶段 2：`S4/S5` final gate candidate 生成与 Gate Direct 契约修复
- 已完成阶段 3：`S3/S4` continuity skill 显式注册 + soft-degraded 可观测化
- 已完成阶段 4：`S3/S5` E2E 改为 hermetic，本地默认回归不再依赖外部 API
- 已补状态可观测性：`soft_degraded_reasons` 已进入 `status` API 与前端进度/工作流视图
- 已补用户态文案映射：前端不再直接显示 `continuity_skill_fallback` 等内部降级码值
- 已补 hermetic 分层：默认 `pytest` 跑 fast 集，完整慢集改走 `make test-hermetic-full`
- 已补 continuity 输入语义：共享 continuity skill 会吸收 `usage_scenario`、storyboard 文本、USP、品牌色；S5 本地 continuity prompt 也保留 `shot_type / product_angle / model_in_shot`
- 已补 S2 品牌语义：`values`、`voice_guidelines`/`tone_of_voice`、`visual_constraints` 已进入 continuity prompt 与 `visual_identity`
- 已补 S3 creator/platform 语义：`influencer_name`、source/target platform、`original_style_preserved` 与 remix `keep_notes` 已进入 continuity prompt；S3 fallback continuity prompt 也保留 creator pacing
- 已补 S5 scene/persona 语义：`scene_id` 场景语义、`story_description`、`selected_models` persona 已进入 continuity prompt 与本地 `visual_identity`
- 已补 S1 platform/brand narrative 语义：`target_platforms`、brand tone、brand colors、`target_audience` 已进入共享 continuity prompt 与 `visual_identity`
- 已补 continuity 导演层结构：共享 continuity `clip_groups` 现在会稳定输出 `scene_beat`、`beat_summary`、`transition_intent`，并被 `seedance-video-prompt` 继续透传
- 已补 S5 本地 continuity 结构对齐：`_vlog_shots_to_clip_groups()` 现在也会输出 `scene_beat`、`beat_summary`、`transition_intent`
- 已补 continuity audit 闭环：`asset_ready_audit` 现在会检查 `director_intent_metadata`，`continuity_score` 与 `continuity_direction_summary` 已开始消费 `scene_beat / transition_intent`
- 已补 gate 评分闭环：`candidate_scorer` 的 clip 评分现在会识别 `Narrative beat / Beat summary / Transition intent`，将其计入 `director_intent` 维度
- 已补前移评分消费：`video_prompts` 新增专用 scorer，`vlog_strategy` scorer 也已开始读取当前真实的 `shots` 结构与导演意图完整性
- 已补 `clip_details` 结构化透传：`S1/S3/S4/S5` 的 `seedance_clips` 现在会直接写入 `scene_beat`、`beat_summary`、`transition_intent`，避免下游继续依赖 prompt 文本反推
- 已补评分优先级收口：`candidate_scorer` 在 `seedance_clips` 上已改成先读结构化 `scene_beat / beat_summary / transition_intent`，文本解析仅保留为 fallback
- 已补 `video_prompts` 同口径收口：`director_intent` 评分现在也先读结构化 `scene_beat / beat_summary / transition_intent`，文本解析只作为 fallback
- 已补状态诊断透传：status / gate 接口现在会直接返回 `continuity_diagnostics`，包括 `continuity_score`、`director_intent_metadata` 和逐段 `clip_directions`
- 已补前端诊断闭环：`StageProgress` 与 `GatePanel` 已开始直接展示这份 `continuity_diagnostics`
- 已补候选卡片摘要：`CandidateSelector` 已开始直接展示候选里的前两段 `scene_beat / transition_intent`
- 已补候选卡片 continuity 得分解释：`CandidateSelector` 现在会直接展示 `score.breakdown.director_intent`
- 已补候选卡片 explanation 排序：`director_intent` 维度现在会在 explanation 文本里优先展示
- 已补 gate/status 摘要顺序统一：`StageProgress` 与 `GatePanel` 现在共用 continuity diagnostics summary helper
- 已补结果页/质量视图 continuity 诊断闭环：`DirectorPlayback` 与 `QualityDashboard` 现在也复用同一份 continuity diagnostics helper，并直接展示逐段 `scene_beat / transition_intent`
- 已补版本对比 continuity 解释：`CompareView` 现在会在版本卡片里直接展示 continuity diagnostics，比较时不再只看总分和 criteria
- 已补选中版本的 continuity verdict：`CompareView` 底部 action 区现在也会对当前选中版本展示同一份 continuity diagnostics，便于最终下载/发布前复核
- 已补 continuity 统一对比表：`CompareView` 的 quality comparison table 现在新增 `Director intent` 与 `Continuity score` 两行，版本间 continuity 维度已进入同一张比较表
- 已补 continuity 表格解释：`CompareView` 的 quality comparison table 现在新增 `Continuity verdict` 行，版本间“为什么 continuity 更好”不再只靠分数推断
- 已做 CompareView continuity 去重：版本卡片保留摘要，逐段导演意图细节收口到统一对比表和已选版本 verdict，避免三层 UI 完全重复
- 已补 CompareView verdict 长度控制：长 `transition_intent` 在表格里会软截断，完整内容保留在 hover `title`，避免多版本对比表被长文案撑宽
- 已补 CompareView continuity section 分组：`Director intent` / `Continuity score` / `Continuity verdict` 现在视觉上归入独立 continuity 区块，不再和普通质量标准混成一串表格行
- 已补 CompareView continuity compact summary：`Director intent` 与 `Continuity score` 现在合并为一行 `Continuity summary`，在不丢信息的前提下继续压缩表格高度
- 已补 CompareView continuity pills：`Continuity summary` 现在用 badge/pill 形式展示状态与分数，继续降低 continuity section 的文字噪音
- 已补 CompareView verdict tooltip：`Continuity verdict` 不再依赖原生 `title`，完整文案现在通过 hover/focus tooltip 暴露，桌面与键盘可读性更稳定
- 已补 verdict tooltip 组件化：`CompareView` 现已通过轻量 `InlineTooltip` 组件承载 continuity verdict 的完整文案展示，避免局部 tooltip 逻辑继续膨胀
- 已补 InlineTooltip 第二落点：`GatePanel` continuity diagnostics 现已复用 `InlineTooltip` 承载长 `beatSummary` / `transitionIntent`，审批界面不再被长文案撑开
- 已补 InlineTooltip 第三落点：`StageProgress` continuity diagnostics 现也复用 `InlineTooltip` 承载长 `beatSummary` / `transitionIntent`，运行中视图与审批中视图的展示口径已对齐
- 已补 InlineTooltip 第四落点：`QualityDashboard` continuity diagnostics 现也复用 `InlineTooltip` 承载长 `transitionIntent`，结果页质量视图与运行中/审批中视图的展示口径已对齐
- 已补 InlineTooltip 第五落点：`DirectorPlayback` continuity diagnostics 现也复用 `InlineTooltip` 承载长 `transitionIntent`，结果层两处视图的展示口径已对齐
- 已补 InlineTooltip 组件收口：现支持 `placement`、默认移动端安全宽度与 `focus/active` 显示，后续若继续扩落点不需要再复制局部 tooltip 逻辑
- 已补 continuity 截断 util 收口：`truncateDiagnosticText()` 现统一落在 `web/src/lib/diagnosticText.ts`，`GatePanel` / `StageProgress` / `QualityDashboard` / `DirectorPlayback` 的局部重复实现已移除
- 已补 `StageProgress` hook warning 收口：stage completion tracking 改用 `ref + stageCompletionKey`，continuity UI 相关 lint debt 不再残留在依赖数组
- 已补 `StageProgress` polling effect suppress 收口：初始轮询 timer 现在通过 `pollRef.current()` 调用最新 callback，不再需要 `exhaustive-deps` 例外
- 已补 `StageProgress` 卸载安全：poll response、completion delay、celebration reset 统一受 mounted guard 保护，unmount 时会清理相关 timer
- 已补 `StageProgress` 轮询失败阈值回归：连续 status 请求失败达到阈值后会停止继续 schedule poll，并显示连接中断提示
- 已补 `StageProgress` 服务端错误态 timer 收口：status 返回 `error` / `pipeline_degraded` 后会停止 elapsed timer，错误页不再后台继续计时
- 已补 `StageProgress` timer cleanup helper：poll timeout、elapsed interval、completion delay、celebration reset 统一通过内部 helper 清理，降低后续漏清理概率
- 已补 `StageProgress` 服务端错误通知去重：同一错误签名只触发一次 `onError`，避免父组件收到重复错误通知
- 已补 `StageProgress` gate pause 通知去重：同一 `current_step` 的 `paused/awaiting_approval` 只触发一次 `onGatePause`
- 已补 `StageProgress` paused 语义回归：等待 gate 审核期间继续 elapsed 计时与 status polling，用于保留总等待时间并感知审批后的恢复
- 已补 `StageProgress` paused polling 降频：进入 `paused/awaiting_approval` 后 status polling 从 2s 调整为 10s，降低等待审核期间的无效请求
- 已补 `StageProgress` polling cadence 常量收口：base/paused/max/failure threshold 提升为模块级常量，避免组件 render 内重复声明
- 已补 `StageProgress` stage definitions 命名收口：局部 `STAGES` 改为 `stageDefs`，明确 stage 定义来自模块级稳定引用，不额外添加 `useMemo`
- 已补 `StageProgress` stage runtime 纯函数：progress、active stage、completion key 统一由 `deriveStageRuntimeState()` 产出，并补直接单测
- 已补 `StageProgress` 剩余时间估算纯函数：`estimateRemainingSeconds()` 现在直接覆盖 early elapsed、complete、同类型平均耗时 fallback 边界
- 已补 `StageProgress` 总进度纯函数：`deriveTotalProgress()` 统一产出 total steps/done/progress，并覆盖空 stage 边界
- 已补 `StageProgress` 初始 polling timer cleanup：启动 effect 复用 `clearPollTimeout()`，首次 status 请求前 unmount 不会再触发后台请求
- 已补 Smart Create 父级错误消费：`page.tsx` 现在把 `StageProgress.onError` 接到执行态恢复逻辑，status `error` / `pipeline_degraded` 会停止 execution bar、清 active pipeline 并弹页面级 toast，进度面板仍保留原始错误详情
- 已补 Smart Create 错误恢复行为回归：`handleSmartCreateStageError()` 直接断言停止生成、清 active pipeline、toast 展示和空错误 fallback，不需要真实 poyo token
- 已补 continuity 规则导演层：`continuity_storyboard_grid` 现在会派生 `director_profile`，将 `story_arc`、`audience_tension`、`brand_promise`、`platform_pacing`、`creator_cadence` 注入 `visual_identity`、`clip_groups` 和 Seedance prompt，仍保持本地 hermetic 可测
- 已补 continuity 测试隔离：`test_registry_execute_uses_safe_execute_path` 恢复全局 `SkillRegistry`，避免污染后续 `seedance-video-prompt` 测试；组合回归 `75 passed, 12 deselected`
- 已完成 LLM director planner 评估：ADR-007 决议当前不把 LLM planner 引入默认 continuity 热路径；未来只能通过 feature flag、schema 校验、超时 fallback 和 deterministic 回退接入
- 已补非 S1 推荐阶段口径：`RecommendPanel` 对 S2-S5 不再调用 `startS1StepByStep()`，改用本地 config 摘要生成推荐面板，避免推荐页行为与“auto + gate”产品边界冲突

### 下一步执行计划

| 优先级 | 行动 | 原因 | 预估工作量 | 验收 |
|---|---|---|---|---|
| **P0** | 收口 `S2-S5` step-by-step 产品边界 | 已完成：后端通用 `step/regenerate` 接通，前端入口、推荐阶段与文档明确为“仅 S1 支持 step-by-step，其他场景走 auto + gate” | 已完成 | 页面、推荐页、文档和后端能力口径一致 |
| **P1** | 决定是否补 `S2-S5` 的前端 step-by-step 交互 | 现在不是底层不可用，而是产品面暂未兑现 | 0.5-1 天 | 若未来补齐，不再需要前端收口逻辑 |
| **P2** | 压缩 hermetic 回归耗时（优先 S3/S5） | 已完成：`S3/S4/S5` 已从约 74s 降到约 25s，`S3+S5` 已降到约 15s | 已完成 | 默认本地 hermetic 回归已达到可接受速度 |
| **P3** | Smart Create 错误恢复链路补可执行测试 | 已完成：恢复逻辑抽成纯函数并补直接单测 | 已完成 | 停止生成、清 active pipeline、toast 与空错误 fallback 均有断言 |
| **P4** | continuity 质量增强：从“输入驱动模板”升级到更强导演语义 | 已完成：规则层新增 `director_profile` 并进入 prompt / identity / clip group | 已完成 | `S1` continuity、`S3/S4/S5` hermetic E2E 和 skill 单测均通过 |
| **P5** | LLM director planner 方案评估 | 已完成：ADR-007 决定默认不接入，未来只允许 feature-flagged 增强 | 已完成 | 架构决策、取舍、rollback 和未来边界已记录 |
| **P6** | 生产 smoke：S3/S4/S5 continuity + gate 真流量验证 | 当前解决的是本地正确性，不是线上真实依赖链 | 0.5 天 + API 额度 | 3 个场景至少各跑 1 次真实链路 |

### 本轮建议执行顺序

1. 在没有 poyo token 前，继续只做 hermetic / mock / unit 层验证
2. 下一个不消耗 poyo token 的优先项是清理剩余前端/文档口径不一致，不做真实视频 smoke
3. 充值后再做 `P6`，补生产真流量 smoke

*报告版本: v1.5 | 基于 poyo.ai 2026-05 catalog + 当前 git working tree | 下一次更新: 生产 smoke 或下一个 hermetic 改进完成后*
