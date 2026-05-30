---
title: S1-S5 视频生成Pipeline深度风险评估与改善优化计划
doc_type: workflow
module: ai-video
topic: pipeline-risk-assessment
status: stable
created: 2026-05-13
updated: 2026-05-31
owner: Cindy
source: ai
---

# S1-S5 视频生成Pipeline深度风险评估与改善优化计划

> **历史语境（2026-05-31）**：本文是 2026-05-13 的深度风险评估快照，保留用于追溯 S1-S5 技术债来源。Top 风险、代码证据和改进建议不代表当前状态；当前关闭项、未闭项和下一步 TODO 以 [`docs/claude/known-gaps-stable.md`](../claude/known-gaps-stable.md) 为准。

> 评估范围：S1 商品直拍 / S2 品牌宣传 / S3 网红二创 / S4 直播拍摄 / S5 品牌VLOG
> 评估依据：`multi-agent-video-system-design.md` + `product-architecture.md` + 当前AI视频生成现状
> 参与agent：@AIVideoIntel (Part 1) / @AIArchitect (Part 2) / @QA (Part 3) / @ComplianceRisk (Part 4) / @Creative (Part 5) / @EcomOps (Part 6)
> 整合：@Cindy

---

## 一、执行摘要

### 1.1 Top 10 风险（按紧急度排序）

| 排名 | 风险ID | 风险描述 | 影响场景 | 风险等级 | 发现来源 |
|:---:|:---|:---|:---|:---:|:---|
| 1 | R-S2-ARCH | S2是60行DEPRECATED wrapper，无独立管线，产品语义与代码语义严重不一致 | S2 | **P0** | Part 1+2+3 三角验证 |
| 2 | R-S5-DURA | S5 15s硬限制，多片段拼接无跨片段一致性，品牌VLOG无法交付30-90s | S5 | **P0** | Part 1+2 |
| 3 | R-GATE-SCORE | Gate评分虚假自信：LLM fallback + 无绝对阈值 + 不分析实际图像，低质量内容可穿越双门 | S1-S5 | **P0** | Part 2+3 |
| 4 | R-TEST-S2 | S2零独立测试，brand_mode合规路径全部未经回归验证 | S2 | **P0** | Part 3 |
| 5 | R-TEST-GATE | Gate 2/3/4无E2E测试，gate_4硬编码0.9，质量门控形同虚设 | S1-S5 | **P0** | Part 3 |
| 6 | R-TEST-SCORER | candidate_scorer 454行6函数零测试，heuristic子串匹配有BLOCK-01同类bug | S1-S5 | **P0** | Part 3 |
| 7 | R-VENDOR-LOCK | 五场景100%走Poyo.ai/Seedance，单供应商锁定构成业务连续性风险 | S1-S5 | **P1** | Part 1+2 |
| 8 | R-S4-CONT | S4 AI补充片段无连续性锚定，镜头间跳跃剪切 | S4 | **P1** | Part 1+2+3 |
| 9 | R-DEGRADE-L2 | 降级链路L1步骤内已实现，L2跨步骤降级未实现，assemble失败即halt全部 | S1-S5 | **P1** | Part 2+3 |
| 10 | R-COST-EXP | Expert模式worst-case 18次Seedance调用，单条成本$11.98，无budget硬上限 | S1-S3 | **P1** | Part 2+3+6 |

### 1.2 Top 10 改进点（按ROI排序）

| 排名 | 改进ID | 改进描述 | 预期收益 | 投入 | ROI | 负责人 |
|:---:|:---|:---|:---|:---|:---:|:---|
| 1 | I-S3-COMP | S3合规自动化拦截（医疗声明禁区+AI标签） | 避免下架/封号 | 低 | **∞** | @ComplianceRisk |
| 2 | I-S4-KEYF | S4补全keyframe层+连续性锚定 | 质量提升+用户体验 | 中 | **15x** | @AIArchitect |
| 3 | I-SCHEMA-V | 状态Schema版本化+场景化P6阈值配置 | 系统可维护性 | 中 | **8x** | @AIArchitect |
| 4 | I-MULTI-FMT | 多平台一键多规格输出（9:16/1:1/16:9） | 运营效率 | 低 | **6x** | @EcomOps |
| 5 | I-MODEL-RT | 建立ModelRouter多模型路由层 | 供应商解耦+能力扩展 | 中 | **5x** | @AIArchitect |
| 6 | I-S2-REBUILD | S2重建为独立管线或正式降级为S1配置变体 | 产品一致性 | 高 | **4x** | @AIArchitect |
| 7 | I-TEST-GATE | Gate 2/3/4 E2E测试+gate_manager retry bug修复 | 质量门控可信 | 中 | **4x** | @QA |
| 8 | I-TEST-SCORER | candidate_scorer完整单元测试+min_threshold=0.60 | 评分算法可信 | 低 | **4x** | @QA |
| 9 | I-S5-VEO | S5接入Veo 3.1（60s单片段）+ VideoContinuityManager | 时长解封 | 中 | **3x** | @AIVideoIntel |
| 10 | I-DIGI-HUM | 集成HeyGen API补齐数字人能力空白 | 竞品对齐 | 低 | **2x** | @EcomOps |

---

## 二、S1-S5 逐场景风险评估矩阵

### 2.1 S1 商品直拍 — Product Direct

| 维度 | 当前状态 | 风险等级 | 关键问题 |
|:---|:---|:---:|:---|
| 管线成熟度 | 最成熟，1155行，12步完整 | ✅ 低 | 基准场景，其他场景参考标准 |
| AI模型适配 | Seedance 2.0，I2V首帧锚定 | P1 | 产品一致性不可控，反射材质失真 |
| 质量门控 | 4-Gate完整，但评分算法有缺陷 | P1 | Gate评分虚假自信，可穿越双门 |
| 测试覆盖 | `test_s1_e2e.py` 286行Skill级 | P1 | 缺StepRunner集成、Gate全流程、降级路径 |
| 时长支持 | 15-90s，continuity chain已实现 | ✅ 低 | 15s×6段拼接，连续性可保障 |
| 成本 | 典型$6.32-10.48/条 | P1 | Expert worst-case $11.98，无budget上限 |
| 运营适配 | 6平台规则已覆盖 | ✅ 低 | 产品卖点穿透型内容，平台接受度高 |

**核心瓶颈**：产品形态在AI生成中易漂移，文字/Logo生成失败率高。建议强制I2V首帧锚定（1周），接入Kling 3.0 POC（2周）。

### 2.2 S2 品牌宣传 — Brand Campaign

| 维度 | 当前状态 | 风险等级 | 关键问题 |
|:---|:---|:---:|:---|
| 管线成熟度 | **60行DEPRECATED wrapper**，delegate S1+brand_mode=True | **P0** | 产品架构文档描述为独立业务线，代码实现为配置变体 |
| AI模型适配 | 与S1完全相同 | P1 | 无独立视觉锚定，品牌调性纯文本驱动 |
| 质量门控 | 复用S1 Gate，无品牌专属评分维度 | P1 | 品牌氛围vs产品一致性权重未区分 |
| 测试覆盖 | **零独立测试** | **P0** | `test_s2_e2e.py`不存在，brand_mode合规路径未验证 |
| 时长支持 | 同S1 | ✅ 低 | — |
| 成本 | 同S1 | P1 | — |
| 运营适配 | 品牌价值观驱动，视觉规范约束 | P1 | 竞品活动参考未接入Pipeline |

**核心瓶颈**：产品语义与代码语义不一致是最大结构性债务。建议立即决策：**A) 降级为S1配置变体**（产品文档同步更新，2天）；**B) 重建独立Pipeline**（品牌专属strategy+视觉规范约束，2-4周）。

### 2.3 S3 网红二创 — Influencer Remix

| 维度 | 当前状态 | 风险等级 | 关键问题 |
|:---|:---|:---:|:---|
| 管线成熟度 | 1015行，video_analysis+character_identity+remix_script | P1 | 链式容错缺测试，LLM失败无 graceful降级 |
| AI模型适配 | I2V+视频分析，人物跨片段漂移 | P1 | 人物一致性难以维持 |
| 质量门控 | 复用S1 Gate | P1 | P6阈值0.85偏严，建议拆分为person_consistency+product_presence |
| 测试覆盖 | `test_s3_e2e.py` 188行Pipeline.run级 | P1 | 缺StepRunner集成、链式容错、Gate审批 |
| 时长支持 | 同S1 | ✅ 低 | — |
| 成本 | 同S1 | P1 | — |
| 运营适配 | 二创合规风险极高 | **P0** | 版权、肖像权、平台二创政策 |

**核心瓶颈**：合规风险是S3的最大威胁。医疗声明禁区+AI生成标签+婴儿影像限制+版权/二创合规，任一违规即下架/封号。建议合规检查前置到Pipeline自动拦截。

### 2.4 S4 直播拍摄 — Live Shoot

| 维度 | 当前状态 | 风险等级 | 关键问题 |
|:---|:---|:---:|:---|
| 管线成熟度 | 524行，7步，**无strategy/storyboard** | P1 | 无策略门控，seedance直接根据text prompt生成 |
| AI模型适配 | T2V+实拍混剪，AI补充片段无连续性 | P1 | 镜头A结尾→镜头B开头跳跃剪切 |
| 质量门控 | **无keyframe层**，Gate 2审clip而非画面 | P1 | 用户无法在视频生成前确认视觉风格 |
| 测试覆盖 | `test_s4_e2e.py` 94行 + footage_behavior | P1 | 缺footage降级、I2V条件生成、无strategy影响验证 |
| 时长支持 | 同S1 | ✅ 低 | — |
| 成本 | 同S1 | P1 | — |
| 运营适配 | 实时互动感需求 | P1 | 直播场景特殊合规（实时审核、虚假宣传） |

**核心瓶颈**：无strategy/storyboard导致生成失控。建议补全keyframe层+VideoContinuityManager，或明确S4的「快创」定位（3-Gate刻意简化）。

### 2.5 S5 品牌VLOG — Brand VLOG

| 维度 | 当前状态 | 风险等级 | 关键问题 |
|:---|:---|:---:|:---|
| 管线成熟度 | 577行，vlog_strategy+shots→scripts adapter | P1 | adapter边界未测试，stub检测前置缺失 |
| AI模型适配 | **15s硬限制**，多片段拼接无一致性 | **P0** | 品牌VLOG需求30-90s，当前最多15s |
| 质量门控 | **无scripts/storyboard/keyframe**，Gate 2直接审clip | P1 | 用户无法预审视觉风格 |
| 测试覆盖 | `test_s5_e2e.py` 113行 | P1 | 缺adapter边界、关键帧锚定、stub检测 |
| 时长支持 | **15s死锁** | **P0** | seedance_video_generate:duration clamped [3,15] |
| 成本 | 同S1 | P1 | — |
| 运营适配 | 生活方式沉浸感需求 | P1 | 叙事连贯性>单帧一致性，需新增narrative_coherence指标 |

**核心瓶颈**：15s硬限制是S5的生死线。短期接入Veo 3.1（60s，2周），中期抽象VideoContinuityManager+评估Wan 2.2自建（1-2月）。

---

## 三、跨场景共性风险与系统性改进

### 3.1 供应商锁定与多模型路由

**现状**：五场景100%走Poyo.ai/Seedance，无多模型路由。`poyo_client.py`母婴术语拦截已构成业务连续性风险。

**建议**：建立`ModelRouter`多模型路由层（2周），与状态机解耦。选型矩阵：

| 场景 | 首选 | 备选 | 降级 |
|:---|:---|:---|:---|
| S1 | Seedance 2.0 | Kling 3.0 | Wan 2.2 |
| S2 | Runway Gen-4 | Veo 3.1 | Wan 2.2 |
| S3 | Kling 3.0 | Seedance 2.0 | — |
| S4 | Seedance 2.0 | Kling 3.0 | ffmpeg stub |
| S5 | Veo 3.1 | Wan 2.2 | Seedance分段 |

### 3.2 Gate评分系统重构

**现状三重缺陷**：
1. LLM评分返回无Pydantic校验，异常fallback到启发式（关键词匹配+字数统计）
2. 关键帧评分仅检查prompt关键词，**不分析实际图像文件**
3. 无绝对阈值：3候选0.42/0.45/0.48仍推荐0.48并标记★

**建议**：
- 热修复（本周）：增加`min_threshold=0.60`，关键帧增加文件存在性校验
- 短期（2周）：关键帧评分升级到GPT-4V/Kimi Vision实际图像分析
- 中期（1月）：评分算法完整单元测试+schema校验

### 3.3 降级链路三级化

**现状矛盾**：L1步骤内降级已实现（单clip失败→继续其他clips），L2跨步骤降级未实现（assemble失败→halt全部后续步骤）。

**建议四级降级**：

| 层级 | 触发条件 | 当前行为 | 建议行为 |
|:---|:---|:---|:---|
| L0 | 单候选失败 | retry 1次（有bug）| 修复retry+budget控制 |
| L1 | 步骤内部分失败 | gather(return_exceptions=True) ✅ | 保持+stub质量验证 |
| L2 | 步骤完全失败 | pipeline_degraded=True → halt ❌ | **返回partial artifacts+标记degraded_reason+允许上游决策** |
| L3 | 核心步骤失败 | halt ✅ | 保持+增加上游重生成或人工介入路径 |

### 3.4 状态Schema版本化

**现状**：S4/S5的`footage_assets`/`scene_map`字段在`VideoPipelineState`中不存在，与LangGraph 16节点管道状态模型不兼容。

**建议**：
- 短期（2周）：状态Schema版本化（MINOR+1），@QA同步准备契约测试断言
- 中期（1月）：明确LangGraph废弃决策或统一状态模型

### 3.5 前端STEP_ORDER动态化

**现状**：前端11步（缺`keyframe_images`）vs后端12步，S1-S3的keyframe步骤在前端不可见。

**建议**：按场景动态渲染STEP_ORDER，S4/S5显示7-8步，S1-S3显示12步。

---

## 四、AI模型能力边界与选型建议

### 4.1 模型适配度评分（综合分，1-5）

| 场景 | Seedance(当前) | Kling 3.0 | Runway Gen-4 | Veo 3.1 | Wan 2.2 |
|:---|:---:|:---:|:---:|:---:|:---:|
| S1 商品直拍 | **2.0** | 3.0 | 3.0 | 3.0 | **3.5** |
| S2 品牌宣传 | **2.0** | 3.0 | **3.5** | 3.5 | 3.5 |
| S3 网红二创 | **2.5** | **3.5** | 3.0 | — | 3.5 |
| S4 实拍真人 | **2.0** | 3.0 | 3.0 | 3.0 | — |
| S5 品牌VLOG | **1.0** | 3.0 | 3.0 | **3.5** | **4.0** |

### 4.2 最高优先级行动建议

| 优先级 | 行动 | 模型 | 周期 | 影响场景 |
|:---:|:---|:---|:---:|:---|
| 1 | 接入Veo 3.1 API | Veo 3.1 | 2周 | S5 |
| 2 | S2架构决策+重建 | — | 2-4周 | S2 |
| 3 | 建立ModelRouter | 多模型 | 2周 | S1-S5 |
| 4 | S1强制I2V首帧锚定 | Seedance | 1周 | S1 |
| 5 | Kling 3.0接入POC | Kling 3.0 | 2周 | S1/S3/S4 |
| 6 | Wan 2.2自建评估 | Wan 2.2 | 1-2月 | S5 |

---

## 五、架构风险与重构建议

### 5.1 Skill复用度优化

**现状**：核心媒体Skill（seedance/tts/assemble/audit）复用度高，但策略/脚本Skill每个场景重复建设。

**建议合并**：
- `product-strategy` + `vlog-strategy` → `content-strategy`（按scenario内部分支）
- `script-writer` + `remix-script` → `script-engine`（按scenario内部分支）

### 5.2 Candidate Budget控制

**现状**：Gate 3生成3个视频片段候选，无budget控制。Gate 1选2个脚本×3片段×3候选=18次视频调用。

**建议**：
- 低分辨率预览候选（ Gate 3 先用 360p 生成，选中后再 upscale）
- Expert模式硬预算上限（如$5/条）

### 5.3 S4/S5 Expert模式必要性评估

**发现**：S4/S5补全keyframe层后审批步骤从3→4，对「快创」产品定位有体验冲击。

**建议产品侧评估**：S4/S5目标用户是「快速出片」，3-Gate可能是刻意简化。Expert模式是否必要？

---

## 六、测试策略补充计划

### 6.1 立即执行（本周）

| 任务 | 优先级 | 负责人 | 验收标准 |
|:---|:---:|:---|:---|
| 创建`test_s2_e2e.py` | P0 | @QA | 覆盖wrapper映射、brand_mode合规路径、极端输入 |
| 创建`test_candidate_scorer.py` | P0 | @QA | 6个评分函数全覆盖，heuristic子串匹配修复 |
| 修复`gate_manager.py:369` retry逻辑 | P0 | @Dev | range解耦，variant循环独立，单元测试通过 |
| Gate评分热修复：min_threshold=0.60 | P0 | @Dev | 低于阈值触发全部重生成 |

### 6.2 两周内执行

| 任务 | 优先级 | 负责人 | 验收标准 |
|:---|:---:|:---|:---|
| Gate 2/3 mock E2E测试 | P1 | @QA | 覆盖keyframe审批、clip选择、双版本对比 |
| P6场景敏感阈值配置化 | P1 | @Dev | `SCENARIO_P6_THRESHOLDS`配置表，S1=0.85/S2=0.80/S3=0.82/S4=0.80 |
| AI非确定性测试框架 | P1 | @QA | `llm_stability`+`media_stability`标记体系 |
| S3链式容错测试 | P1 | @QA | video_analysis→character_identity→remix_script完整降级路径 |
| 创建`test_s5_degraded.py` | P1 | @QA | 验证LLM fallback + adapter边界 |

### 6.3 一月内执行

| 任务 | 优先级 | 负责人 | 验收标准 |
|:---|:---:|:---|:---|
| L2跨步骤降级实现 | P2 | @Dev | step_runner.resume()识别degraded_reason，state_manager保存partial_artifacts |
| Gate 4动态评分 | P2 | @Dev | 替代硬编码0.9，基于audit实际结果 |
| PG→SQLite故障模拟测试 | P2 | @QA | 模拟PG故障触发SQLite fallback |

### 6.4 AI非确定性测试四策略

| 策略 | 目标 | 实现方式 |
|:---|:---|:---|
| 契约稳定性测试 | LLM输出结构稳定 | 同prompt运行5次，比较schema字段存在性+类型 |
| 统计稳定性测试 | 关键指标稳定 | USP覆盖率多次采样，验证均值≥80%且方差<0.15 |
| 媒体生成回归测试 | 媒体输出一致 | 同prompt生成两次，验证duration/file_size一致性 |
| 影子测试 | 真实API回归 | CI中可选真实调用（默认skip，`-m llm_stability`手动触发） |

---

## 七、合规风险清单

### 7.1 合规特有 CRITICAL 风险（@ComplianceRisk Part 4）

| 发现ID | 风险描述 | 影响场景 | 等级 | 关联风险 |
|:---|:---|:---|:---:|:---|
| COMP-CRIT-1 | **S3 网红二创**：版权/肖像权/原作者违规残留三重风险，当前无remix前预审机制 | S3 | **P0** | R-S3-REMIX |
| COMP-CRIT-2 | **S4 直播拍摄**：实时审核缺口 + 口头声明失控 + 素材版权溯源缺失 | S4 | **P0** | R-S4-LIVE |
| COMP-CRIT-3 | **S5 品牌VLOG**：nursery/儿童房场景默认涉及儿童影像，COPPA + 肖像权双重风险 | S5 | **P0** | R-S5-VLOG |
| COMP-WARN-1 | S2为deprecated wrapper，brand_mode下品牌价值观/社会议题风险未被独立覆盖 | S2 | **P1** | R-S2-ARCH |
| COMP-WARN-2 | AI生成内容标注（C2PA/元数据）全场景缺失，EU AI Act 2026-08-02生效后面临高额罚款 | S1-S5 | **P1** | R-AI-LABEL |
| COMP-WARN-3 | candidate_scorer / Gate评分对合规维度零覆盖，医疗声明等风险无法被AI评分识别 | S1-S5 | **P1** | R-GATE-SCORE |
| COMP-WARN-4 | 跨场景状态Schema无版本化，合规规则可能随代码变更漂移 | S1-S5 | **P1** | R-SCHEMA-VERSION |
| COMP-WARN-5 | 东南亚/中东区域合规规则未配置化，扩张时面临碎片化合规成本 | S1-S5 | **P1** | R-REGION-EXP |

### 7.2 五场景 × 四平台合规矩阵

#### 7.2.1 医疗/功效声明禁区

| 场景 | TikTok | Meta/FB | YouTube | Amazon | 风险等级 |
|:---|:---|:---|:---|:---|:---:|
| S1 商品直拍 | 极严：禁用「治疗」「预防」「改善」 | 极严：FDA医疗宣称规则 | 严格：需科学证据支撑 | 极严：A9算法+人工双审 | **P0** |
| S2 品牌宣传 | 严格：品牌价值观不可涉医疗 | 严格：社会福利/健康暗示受限 | 中等：品牌故事相对宽松 | 中等：A+页面需合规 | **P1** |
| S3 网红二创 | 极严：UGC医疗声明=平台连带责任 | 极严：influencer医疗推荐=高风险 | 严格：需disclaimer | — | **P0** |
| S4 直播拍摄 | 极严：实时口头声明不可控 | 极严：live声明无edit缓冲 | 严格：回放保留证据 | — | **P0** |
| S5 品牌VLOG | 严格：生活方式隐含健康暗示 | 严格：nursery场景=儿童内容加强审查 | 中等：纪录片风格相对宽松 | — | **P1** |

**母婴品类高危词库**：治疗、预防、改善、益智、抗过敏、助眠、发育促进、免疫力提升、医疗级、临床验证（无批文时）。

#### 7.2.2 AI生成内容披露

| 平台 | 披露要求 | 处罚方式 | 生效时间 |
|:---|:---|:---|:---|
| TikTok | 需标注「AI生成」标签 | 限流/下架 | 已生效 |
| Meta/FB | 广告需标注「AI生成」 | 广告拒登/账号警告 | 已生效 |
| YouTube | 需标注+元数据标记 | 限流/ demonetization | 已生效 |
| Amazon | A+内容需声明AI使用 | Listing下架 | 已生效 |
| **EU全域** | **C2PA强制水印+元数据** | **高额罚款（最高3500万或全球营收7%）** | **2026-08-02** |

**紧急行动**：EU AI Act 8月2日生效，当前全场景C2PA标注缺失，需在7月底前完成技术接入。

#### 7.2.3 婴儿/儿童影像使用限制

| 场景 | COPPA(US) | GDPR-K(EU) | 平台政策 | 建议 |
|:---|:---|:---|:---|:---|
| S1 | 产品展示可不含儿童 | 需家长同意 | 相对宽松 | 可用产品特写替代 |
| S2 | 品牌宣传中儿童出现需审查 | 高敏感 | 严格 | 建议用抽象化/动画替代 |
| S3 | remix原视频含儿童=高风险 | 高风险 | 极严 | 必须原视频授权+儿童监护人同意 |
| S4 | 直播中含儿童=实时COPPA触发 | 实时GDPR-K触发 | 极严 | 建议禁止儿童入镜 |
| **S5** | **nursery/儿童房场景=默认儿童出现** | **默认高敏感** | **极严** | **建立「AI生成可识别儿童形象禁令」** |

**关键建议**：本项目应建立「AI生成可识别儿童形象禁令」。替代方案：
1. 真实拍摄+监护人书面授权
2. 抽象化表达（剪影、背影、无面部特征）
3. 第一人称视角（父母视角，不出现儿童面部）

#### 7.2.4 版权与二创合规

| 层级 | S3 网红二创风险 | 当前覆盖 | 建议 |
|:---|:---|:---:|:---|
| L1 原视频授权 | 是否获得原视频使用授权 | ❌ 无 | remix前强制授权验证 |
| L2 肖像权 | 原视频中人物肖像权 | ❌ 无 | 人物识别→肖像权扫描 |
| L3 改编权 | 二次创作是否构成改编 | ❌ 无 | 法律review+改编比例阈值 |
| L4 平台政策 | 各平台对二创的态度差异 | ❌ 无 | 分平台二创政策配置 |

#### 7.2.5 直播场景特殊合规

| 风险点 | 描述 | 严重程度 |
|:---|:---|:---:|
| 实时审核延迟 | AI审核有秒级延迟，口头违规声明可能已传播 | **P0** |
| 口头声明失控 | 主播即兴发言超出脚本审核范围 | **P0** |
| 用户互动风险 | 评论区用户提及医疗效果，主播回应可能构成背书 | **P1** |
| 回放证据保留 | 直播回放作为法律证据，需长期保留 | **P1** |
| 素材版权溯源 | 直播中使用背景音乐/视频素材的版权 | **P1** |

### 7.3 区域差异清单

| 区域 | 核心法规 | 母婴特殊要求 | 紧急度 |
|:---|:---|:---|:---:|
| **北美** | FTC/FDA/COPPA/CCPA | FDA对婴儿食品/辅食严格；CPSC对玩具进口申报 | P1 |
| **欧洲** | **EU AI Act/GDPR-K/AVMSD/DSA** | **C2PA强制（8月2日）**；GDPR-K对儿童数据极严 | **P0** |
| **东南亚** | 各国碎片化 | TikTok Shop/Shopee Live合规优先；无统一标准 | P1 |
| **中东** | 宗教文化极度敏感 | 哺乳画面/性别同框/儿童影像需本地审核；无统一法规 | **P1** |

### 7.4 合规自动化拦截建议

#### 可自动拦截（8项）

| 拦截点 | 触发条件 | 执行位置 | 技术方案 |
|:---|:---|:---|:---|
| 医疗禁用词过滤 | 脚本含高危医疗词汇 | Gate 1 | 关键词库+LLM语义检测 |
| FDA认证校验 | 产品声明涉及FDA范围 | Gate 1 | 产品数据库交叉验证 |
| AI生成标签自动添加 | 全部AI生成内容 | 发布前 | C2PA元数据注入 |
| COPPA初筛 | 内容含儿童相关场景 | Gate 2 | 视觉识别+场景标签 |
| 版权指纹匹配 | S3 remix素材 | remix前 | 音频/视频指纹库比对 |
| 平台时长校验 | 超出平台限制 | Gate 4 | 配置化规则引擎 |
| 区域合规路由 | 目标市场自动匹配 | 发布前 | 区域×平台规则矩阵 |
| 实时直播关键词拦截 | 直播中出现高危词 | S4实时 | 语音识别+关键词库 |

#### 必须人工审核（7项）

| 审核点 | 原因 | 执行位置 |
|:---|:---|:---|
| 医疗语境判断 | 同一词汇在不同语境含义不同 | Gate 1 |
| 品牌价值观/社会议题 | 涉及政治、宗教、性别等敏感话题 | Gate 1 |
| 伦理审查 | 儿童影像、身体暴露、暴力暗示 | Gate 2 |
| 跨文化敏感 | 中东/东南亚等特殊文化禁忌 | Gate 2 |
| 版权法律判断 | 改编比例、合理使用边界 | Gate 3 |
| 肖像权授权审核 | 真人面部、可识别特征 | Gate 3 |
| 危机内容终审 | 品牌危机、竞品攻击、负面事件 | Gate 4 |

### 7.5 五层合规架构建议

```
Layer 1: 预生成拦截 — 关键词/认证/版权指纹
Layer 2: 生成中标记 — AI生成标签/COPPA标记/区域标记
Layer 3: 生成后审核 — Gate 1-4合规维度嵌入
Layer 4: 发布前人工 — 7项必须人工审核点
Layer 5: 发布后监控 — 平台投诉/下架/账号健康追踪
```

### 7.6 合规P0行动项（本周必须启动）

| ID | 行动 | Owner | 验收标准 |
|:---|:---|:---|:---|
| COMP-P0-1 | 医疗禁用词库扩展（200+词汇） | @ComplianceRisk | 词库覆盖FDA/FTC/平台禁用词 |
| COMP-P0-2 | AI生成内容标注规则制定 | @Dev + @ComplianceRisk | C2PA元数据格式确认 |
| COMP-P0-3 | S5儿童影像决策：禁令/授权/抽象化 | @ProductAI | 决策文档+技术路径 |
| COMP-P0-4 | S3版权预审机制设计 | @AIArchitect | 授权验证流程图 |
| COMP-P0-5 | S4直播监督机制（实时关键词拦截） | @Dev | 语音识别+关键词拦截POC |

---

## 八、内容质量框架升级方案

### 8.1 当前框架核心缺陷（@Creative Part 5）

| ID | 发现 | 等级 | 关联风险 |
|:---|:---|:---:|:---|
| CQ-1 | 当前7 criteria是「存在性检查」而非「质量评估」，无法区分及格与优秀 | **P0** | R-GATE-SCORE |
| CQ-2 | candidate_scorer 5维度权重未场景化，S2品牌氛围与S1产品卖点共用同一公式 | **P0** | R-S2-ARCH |
| CQ-3 | 3 briefs覆盖5场景结构性缺口，S3/S5无适配模板 | **P1** | R-TEST-GATE |
| CQ-4 | keyframe生成提示词跨场景复用，存在「一个模板套所有」风险 | **P1** | R-S4-CONT |
| CQ-5 | AI评分对「文本结构」可靠，对「视觉质量/情感共鸣/品牌调性」不可信，但Gate决策100%依赖AI评分 | **P0** | R-GATE-SCORE |

### 8.2 五场景内容质量评分框架

#### 通用层（G1-G10，所有场景共享）

| 维度 | 定义 | 评估方式 |
|:---|:---|:---:|
| G1 结构完整性 | 脚本包含hook、卖点、证据、CTA四段 | AI可评 |
| G2 文本准确性 | 无错别字、语法正确、术语统一 | AI可评 |
| G3 卖点覆盖率 | USP在脚本中被提及的比例 | AI可评 |
| G4 时长合规性 | 符合平台时长限制和产品档位 | AI可评 |
| G5 平台规范度 | 含必要的#ad标签、音乐版权说明等 | AI可评 |
| G6 视觉一致性 | 关键帧风格与品牌视觉规范一致 | **人工必审** |
| G7 情感共鸣度 | 内容是否能触发目标用户情绪反应 | **人工必审** |
| G8 品牌调性度 | 表达风格与品牌do/dont一致 | **人工必审** |
| G9 转化清晰度 | CTA明确、购买路径无摩擦 | **人工必审** |
| G10 差异化度 | 与竞品内容有明显区隔 | **人工必审** |

#### 场景专属层（每场景6维度）

**S1 商品直拍**（通用40% / 专属60%）

| 维度 | 权重 | 评估方式 |
|:---|:---:|:---:|
| S1-1 产品卖点穿透度 | 15% | **人工必审** |
| S1-2 痛点共鸣度 | 15% | **人工必审** |
| S1-3 使用场景还原度 | 10% | AI可评 |
| S1-4 竞品差异化表达 | 10% | **人工必审** |
| S1-5 产品形态准确度 | 5% | AI可评 |
| S1-6 CTA紧迫感 | 5% | AI可评 |

**S2 品牌宣传**（通用35% / 专属65%）

| 维度 | 权重 | 评估方式 |
|:---|:---:|:---:|
| S2-1 品牌价值传递准确度 | 20% | **人工必审** |
| S2-2 情感曲线设计 | 15% | **人工必审** |
| S2-3 视觉规范一致性 | 10% | **人工必审** |
| S2-4 品牌故事完整性 | 10% | AI可评 |
| S2-5 竞品区隔度 | 5% | **人工必审** |
| S2-6 价值观共鸣度 | 5% | **人工必审** |

**S3 网红二创**（通用40% / 专属60%）

| 维度 | 权重 | 评估方式 |
|:---|:---:|:---:|
| S3-1 原生感/真实感 | 20% | **人工必审** |
| S3-2 产品植入自然度 | 15% | **人工必审** |
| S3-3 二创合规度 | 10% | AI可评 |
| S3-4 人物一致性 | 5% | AI可评 |
| S3-5 原创素材尊重度 | 5% | **人工必审** |
| S3-6 粉丝语境适配度 | 5% | **人工必审** |

**S4 直播拍摄**（通用45% / 专属55%）

| 维度 | 权重 | 评估方式 |
|:---|:---:|:---:|
| S4-1 实时互动感 | 15% | **人工必审** |
| S4-2 信息密度 | 10% | AI可评 |
| S4-3 镜头语言多样性 | 10% | **人工必审** |
| S4-4 节奏控制力 | 5% | **人工必审** |
| S4-5 即兴真实感 | 5% | **人工必审** |
| S4-6 促销紧迫感 | 10% | AI可评 |

**S5 品牌VLOG**（通用30% / 专属70%）

| 维度 | 权重 | 评估方式 |
|:---|:---:|:---:|
| S5-1 生活方式沉浸感 | 20% | **人工必审** |
| S5-2 叙事连贯性 | 15% | **人工必审** |
| S5-3 情绪曲线 | 10% | **人工必审** |
| S5-4 品牌调性一致性 | 10% | **人工必审** |
| S5-5 场景真实度 | 10% | AI可评 |
| S5-6 价值传递自然度 | 5% | **人工必审** |

### 8.3 脚本模板扩展建议

当前3 briefs（standard/creative/conservative）不足以覆盖5场景。建议扩展为8模板体系：

| 模板ID | 名称 | 适用场景 | 核心定位 |
|:---|:---|:---:|:---|
| `product_focus` | 产品聚焦型 | S1 | 痛点→卖点→证据→CTA |
| `brand_hero` | 品牌故事型 | S2 | 创始人/品牌理念→情感共鸣 |
| `brand_emotion` | 品牌情绪型 | S2 | 氛围营造→价值观传递 |
| `stealth_remix` | 隐性植入型 | S3 | 原生内容→软性产品露出 |
| `compare_review` | 对比测评型 | S3 | 真实体验→客观推荐 |
| `live_demo` | 实时演示型 | S4 | 产品使用→即时互动→限时优惠 |
| `live_qa` | 实时问答型 | S4 | 用户问题→专业解答→信任建立 |
| `day_in_life` | 生活方式型 | S5 | 场景沉浸→品牌自然融入 |
| `scene_immersion` | 场景沉浸型 | S5 | 多场景切换→生活方式表达 |
| `brand_docu` | 品牌纪录型 | S5 | 纪实风格→品牌深度传递 |

**前端策略**：按场景推送子集，非全量展示。S1默认3模板，S2/S3/S4/S5各推送4-5模板。

### 8.4 视觉叙事差异化

五场景视觉策略矩阵（可直接注入pipeline的`visual_strategy` JSON配置）：

| 维度 | S1 | S2 | S3 | S4 | S5 |
|:---|:---|:---|:---|:---|:---|
| **构图** | 中心对称，产品 dominant | 三分法，人物 dominant | 手持/自然，人物 dominant | 多变，产品+人物混合 | 广角/全景，场景 dominant |
| **光线** | 明亮均匀，消除阴影 | 戏剧化，强调情绪 | 自然光，模拟真实环境 | 混合光源，适应直播环境 | 柔和自然， golden hour |
| **色彩** | 高饱和，产品色突出 | 品牌色系，一致性 | 低饱和，原生感 | 动态调整，适应产品 | 暖色调，生活感 |
| **镜头语言** | 固定+推轨，产品特写 | 慢推+浅景深，氛围 | 手持晃动，第一人称 | 快速切换，多角度 | 长镜头+航拍，沉浸 |
| **运动** | 平滑，产品旋转 | 缓慢，情绪铺垫 | 自然，跟随人物 | 快速，匹配节奏 | 流动，场景转换 |

**风险识别**：S3「原生感」与S1「专业感」在keyframe提示词层面存在视觉冲突。需确保`visual_strategy`按场景隔离，禁止跨场景混用。

### 8.5 AI评分可信度矩阵与Gate决策调整

| 评估层 | 维度示例 | AI可信度 | Gate决策建议 |
|:---|:---|:---:|:---|
| 结构层 | 字段完整性、时长、格式 | **高** | AI评分可直接使用 |
| 文本层 | 错别字、语法、USP覆盖率 | **高** | AI评分可直接使用 |
| 语义层 | 情感共鸣、品牌调性、差异化 | **低** | **人工必审，AI评分仅供参考** |
| 视觉层 | 构图、光线、色彩一致性 | **低** | **人工必审，AI评分仅供参考** |
| 转化层 | CTA清晰度、紧迫感、路径 friction | **中** | AI评分+人工复核 |

**历史立即行动建议**：

> 这些建议保留为 2026-05-13 审计输出。当前执行顺序以 [`docs/claude/known-gaps-stable.md`](../claude/known-gaps-stable.md) 为准。

- Gate 1/3取消AI推荐默认选中，强制人工确认
- candidate_scorer增加`heuristic`标识暴露到前端，提示用户当前评分为算法估算
- 7 criteria扩展为「7+5双层审计」：7项基础存在性检查 + 5项质量评估（3项AI+2项人工）

---

## 九、运营落地适配矩阵

### 9.1 五场景 × 六平台规则差异

| 平台 | S1最佳时长 | S2最佳时长 | S3最佳时长 | S4最佳时长 | S5最佳时长 | 特殊规则 |
|:---|:---:|:---:|:---:|:---:|:---:|:---|
| TikTok | 15-30s | 30-60s | 15-30s | 60s+ | 30-60s | #ad标签、音乐版权 |
| IG Reels | 15-30s | 30-90s | 15-30s | 90s | 30-90s | 购物标签、合作披露 |
| YT Shorts | 15-60s | 30-60s | 15-60s | 60s | 30-60s | AI标签、COPPA合规 |
| Amazon | 15-30s | 30-60s | — | 60s+ | — | A+内容规范、认证标识 |
| Facebook | 15-30s | 30-90s | 15-30s | 60s+ | 30-90s | #ad标签、医疗禁区 |
| Shopify | 15-60s | 30-90s | — | — | 30-90s | 产品页嵌入、加载优化 |

### 9.2 竞品差异化定位

| 竞品 | 核心能力 | Hermes差距 | Hermes优势 |
|:---|:---|:---|:---|
| HeyGen | 数字人+多语言 | 数字人能力空白 | 母婴合规深度、多场景覆盖 |
| Colossyan | 企业培训视频 | 企业场景弱 | 电商垂直、运营数据闭环 |
| Synthesia | 企业数字人 | 数字人能力空白 | 母婴品类理解、平台适配 |
| 剪映 | 模板化快剪 | AI生成深度弱 | 端到端AI生成、4-Gate质量 |
| CapCut Commerce | 电商模板 | 场景覆盖少 | 5场景完整管线、策略深度 |

### 9.3 ROI测算摘要

| 场景 | 典型成本/条 | worst-case/条 | 盈亏平衡播放数 | @50K播放ROI |
|:---|:---:|:---:|:---:|:---:|
| S1 | $6.32-10.48 | $11.98 | 3,500-8,000 | 8.5x |
| S2 | $6.32-10.48 | $11.98 | 5,000-10,000 | 6.2x |
| S3 | $6.32-10.48 | $11.98 | 4,000-14,000 | 5.8x |
| S4 | $6.32-10.48 | $11.98 | 6,000-12,000 | 4.5x |
| S5 | $6.32-10.48 | $11.98 | 8,000-14,000 | 3.2x |

**成本结构**：AI生成 $0.32-1.98（含worst-case）+ 人工审核 $6-10。人工是主要成本，自动化审核可显著改善ROI。

---

## 十、改善计划路线图

### 10.1 P0 — 立即执行（本周内）

| ID | 行动 | Owner | 验收标准 | 阻塞项 |
|:---|:---|:---|:---|:---|
| P0-1 | S2架构决策：独立管线or配置变体 | @ProductAI | 决策文档+代码路径确认 | 需@bestore-pray确认 |
| P0-2 | Gate评分热修复：min_threshold=0.60 | @Dev | 低于阈值触发全部重生成 | — |
| P0-3 | 创建test_s2_e2e.py | @QA | 覆盖wrapper映射+brand_mode路径 | 需P0-1决策 |
| P0-4 | 创建test_candidate_scorer.py | @QA | 6函数全覆盖+子串匹配修复 | — |
| P0-5 | 修复gate_manager.py retry bug | @Dev | range解耦+单元测试通过 | — |
| P0-6 | 前端STEP_ORDER动态化 | @Dev | 按场景渲染正确步数 | — |

### 10.2 P1 — 短期执行（2周内）

| ID | 行动 | Owner | 验收标准 | 阻塞项 |
|:---|:---|:---|:---|:---|
| P1-1 | 建立ModelRouter多模型路由层 | @AIArchitect | Seedance/Kling/Veo可切换 | — |
| P1-2 | S5接入Veo 3.1 API（60s） | @AIVideoIntel | S5可生成60s单片段 | 需P1-1 |
| P1-3 | 抽象VideoContinuityManager Skill | @AIArchitect | S4/S5接入连续性链 | — |
| P1-4 | S4/S5补全keyframe层 | @AIArchitect | Gate 2可审画面 | 需产品侧UX评估 |
| P1-5 | P6场景敏感阈值配置化 | @Dev | SCENARIO_P6_THRESHOLDS表 | — |
| P1-6 | Gate 2/3 mock E2E测试 | @QA | 覆盖审批全路径 | — |
| P1-7 | AI非确定性测试框架 | @QA | llm_stability+media_stability | — |
| P1-8 | Candidate Budget硬上限 | @Dev | Expert模式$5/条上限 | — |
| P1-9 | 状态Schema版本化 | @AIArchitect | MINOR+1+契约测试 | — |
| P1-10 | S3合规自动化拦截（初步） | @ComplianceRisk | 医疗关键词过滤 | — |

### 10.3 P2 — 中期执行（1月内）

| ID | 行动 | Owner | 验收标准 |
|:---|:---|:---|:---|
| P2-1 | S2重建为独立管线（如P0-1决策为重建） | @AIArchitect | 品牌专属strategy+视觉规范 |
| P2-2 | Kling 3.0接入POC | @AIVideoIntel | S1/S3/S4可切换Kling |
| P2-3 | 关键帧评分升级到GPT-4V/Kimi Vision | @Dev | 实际图像分析替代prompt关键词 |
| P2-4 | L2跨步骤降级实现 | @Dev | partial artifacts+degraded_reason |
| P2-5 | Gate 4动态评分 | @Dev | 基于audit实际结果 |
| P2-6 | Wan 2.2自建评估 | @AIVideoIntel | 部署可行性报告 |
| P2-7 | 集成HeyGen API补齐数字人 | @EcomOps | POC验证+ROI评估 |
| P2-8 | 多平台一键多规格输出 | @EcomOps | 9:16/1:1/16:9自动适配 |
| P2-9 | 运营数据反向驱动Pipeline | @EcomOps | P8 Publish Tracking数据回流 |
| P2-10 | LangGraph废弃或统一决策 | @AIArchitect | 技术决策文档 |

### 10.4 风险-改善映射总表

| 风险ID | 风险描述 | 对应改进ID | 优先级 | 状态 |
|:---|:---|:---|:---:|:---|
| R-S2-ARCH | S2伪独立管线 | I-S2-REBUILD / P0-1 | P0 | 待决策 |
| R-S5-DURA | S5 15s硬限制 | I-S5-VEO / P1-2 | P0 | 规划中 |
| R-GATE-SCORE | Gate评分虚假自信 | I-TEST-SCORER / P0-2,4 | P0 | 规划中 |
| R-TEST-S2 | S2零测试 | P0-3 | P0 | 规划中 |
| R-TEST-GATE | Gate 2/3/4无E2E | I-TEST-GATE / P1-6 | P0 | 规划中 |
| R-TEST-SCORER | candidate_scorer零测试 | I-TEST-SCORER / P0-4 | P0 | 规划中 |
| R-VENDOR-LOCK | 单供应商锁定 | I-MODEL-RT / P1-1 | P1 | 规划中 |
| R-S4-CONT | S4连续性跳跃 | I-S4-KEYF / P1-3,4 | P1 | 规划中 |
| R-DEGRADE-L2 | L2降级未实现 | P2-4 | P1 | 规划中 |
| R-COST-EXP | Expert成本失控 | P1-8 | P1 | 规划中 |

---

## 附录

### A. 参与Agent与交付物

| Agent | Part | 交付物 | 状态 |
|:---|:---:|:---|:---:|
| @AIVideoIntel | 1 | AI模型能力边界评估 | ✅ 已纳入 |
| @AIArchitect | 2 | 架构风险与跨场景复用评估 | ✅ 已纳入 |
| @QA | 3 | E2E测试缺口矩阵 | ✅ 已纳入 |
| @ComplianceRisk | 4 | 合规风险清单 | ✅ 已纳入 |
| @Creative | 5 | 内容质量评分框架 | ✅ 已纳入 |
| @EcomOps | 6 | 运营策略平台适配 | ✅ 已纳入 |

### B. 历史代码证据索引

> 本索引保留原始审计证据，不保证与当前工作树完全一致。当前边界状态请先查 [`docs/claude/known-gaps-stable.md`](../claude/known-gaps-stable.md)。

| 文件 | 关键行号 | 问题 |
|:---|:---|:---|
| `s2_brand_pipeline.py` | 全文件 | 冻结兼容 shim；warning-only alias to S2 v2 |
| `s5_brand_vlog_pipeline.py` | VIDEO_MAX_DURATION=15 | 15s硬限制 |
| `candidate_scorer.py` | 454行6函数 | 零测试+heuristic缺陷 |
| `gate_manager.py` | L369 | retry逻辑bug |
| `gate_manager.py` | L312 | Gate 4硬编码0.9 |
| `step_runner.py` | L328 | brand_mode仅控制compliance跳过 |
| `poyo_client.py` | — | 母婴术语拦截 |
| `s4_live_shoot_pipeline.py` | 全文件524行 | 无last_frame_path |

### C. 交叉评审共识记录

| 共识项 | Part来源 | 综合结论 |
|:---|:---|:---|
| S2伪独立管线 | 1+2+3 | 产品语义vs代码语义不一致，需立即决策 |
| S5 15s+continuity | 1+2 | 模型边界+架构未补偿双重缺口 |
| Gate评分虚假自信 | 2+3 | 评分算法未经验证即投入Gate决策 |
| 双门漏检 | 1+2+3 | AI评分+审计叠加失效，系统性漏检 |
| L0-L3降级分级 | 2+3 | 四级分级比三档更精细，已对齐 |
| Expert成本$11.98 | 2+3+6 | 18次调用worst-case，需budget硬上限 |
| VideoContinuityManager | 1+2 | 中长期必建设施，与模型选型正交 |

---

---

## D. 决策记录

| 时间 | 决策项 | 决策 | 执行Owner | 预期交付 |
|:---|:---|:---|:---|:---|
| 2026-05-13 10:11 | S2架构 | **重建独立管线** | @AIArchitect | 架构设计草案（本周）+ 完整重建（2-4周） |
| 2026-05-13 10:11 | S5儿童影像 | **授权模式**（监护人书面授权） | @ComplianceRisk | 授权协议模板+checklist（2工作日） |
| 2026-05-13 10:11 | EU AI Act | **预备实施**（C2PA标注） | @ComplianceRisk + @Dev | 技术需求文档（3工作日）+ 7月底前完成接入 |
| 2026-05-13 10:11 | Gate评分热修复 | **min_threshold=0.60，本周实施** | @Dev + @QA | 热修复代码（本周）+ 单元测试 + 契约断言 |
| 2026-05-13 10:17 | S2模型选型边界 | **仅限poyo.ai涵盖模型**（Seedance/Kling/Wan等），参照其官网能力矩阵 | @AIArchitect + @AIVideoIntel | 模型选型适配表（本周） |
| 2026-05-13 10:17 | S5儿童影像处理 | **抽象化处理**（非真实儿童面部），nursery场景暂不纳入，后续可添加 | @Creative + @ComplianceRisk | 抽象化视觉规范 + 平台内容政策对照（2工作日） |
| 2026-05-13 10:17 | Gate评分threshold | **按模型差异化设置**：Seedance 0.65 / Kling 0.60 / Hunyuan&Wan 0.55 / Veo 0.58，非统一线 | @Dev + @Data | 模型-threshold映射表 + 敏感性验证（本周） |

### 决策后Agent执行状态

| Agent | 负责项 | 状态 |
|:---|:---|:---:|
| @AIArchitect | S2独立管线架构设计草案 + poyo.ai模型边界对齐 | ✅ 已交付，`drafts/architecture/s2-brand-campaign-pipeline-design-draft-20260513.md` |
| @AIVideoIntel | S2/S5模型选型评估（poyo.ai能力矩阵）+ threshold建议值已输出 | ✅ 已交付，`drafts/analysis/poyoai-constrained-model-selection-threshold-config-draft-20260513.md` |
| @ComplianceRisk | S5抽象化内容政策对照 + EU AI Act C2PA技术需求 | ✅ 已交付，`drafts/analysis/eu-ai-act-c2pa-gap-assessment-draft-20260513.md` |
| @Dev | Gate模型差异化threshold热修复 + C2PA技术接入 | 待确认 |
| @QA | candidate_scorer单元测试（多threshold分支）+ test_s2_e2e.py | ✅ 已交付：64 passed / 4 xfailed / 4 skipped |
| @Creative | S5儿童影像抽象化视觉规范 + 分级处理 | 已交付（4处代码修改） |
| @EcomOps | 平台适配矩阵AI披露列 + S5授权字段（改为抽象化标注） | ✅ 已交付，`drafts/analysis/ecomops-part6-decision-followup-update-draft-20260513.md` |
| @Data | 模型-threshold敏感性分析（必选） | 已确认计划，待历史数据 |

---

*报告版本: v1.0-stable-1 | 全部6 Parts已纳入 | 7项决策已记录 | 下次更新: 决策执行里程碑达成后*
