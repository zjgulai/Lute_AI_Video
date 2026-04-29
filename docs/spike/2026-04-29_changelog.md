# 2026-04-28/29 改动记录

> 全链路优化、英文母语版本、Expert Studio 双模式架构、6 P0 修复、策略质量提升

## 后端改动

| 文件 | 改动概述 |
|------|---------|
| `src/api.py` | +load_dotenv(), +4个Gate端点, +StepRunner统一auto执行路径, +S3 video_duration参数, +翻译层中文检测 |
| `src/config.py` | +structlog.configure(ConsoleRenderer) 修复 logger.error(error=...) |
| `src/models/__init__.py` | +PRODUCT_DIRECT = "product_direct" 到 ContentScenario |
| `src/pipeline/gate_manager.py` | NEW — 4 Gate定义，候选生成与审批，错误候选排除 |
| `src/pipeline/candidate_scorer.py` | NEW — LLM+启发式候选评分 |
| `src/pipeline/step_runner.py` | +GATE_AFTER_STEPS，+gate暂停逻辑，+gate恢复检查 |
| `src/pipeline/step_editor.py` | +keyframe_images 到 STEP_ORDER |
| `src/pipeline/s1_product_pipeline.py` | +_step_keyframe_images，+_step_quality_gate，+continuity_chain，+duration clamp 5-tier，+target_language硬锁定en |
| `src/pipeline/s3_remix_pipeline.py` | +character_identity，+keyframe_images，+continuity_chain，+video_duration参数，+duration 5-tier clamp |
| `src/skills/product_strategy.py` | 5 briefs→3, 校验修复替代丢弃, +Data Usage Rules段, +Product Context段, +品牌do/dont指令 |
| `src/skills/script_writer.py` | +asyncio.gather并行化, +variant参数(temperature), +EN系统提示词 |
| `src/skills/character_identity.py` | NEW — 人脸检测+CLIP嵌入+OOM防护 |
| `src/skills/keyframe_images.py` | NEW — GPT-Image关键帧生成+shot上限 |
| `src/skills/media_quality_audit.py` | +face_consistency, +product_shape, +motion_smoothness, +空列表保护, +除零保护 |
| `src/skills/seedance_video_generate.py` | +image_to_video, +_extract_last_frame, +continuity_frame_path, +时长越界保护, +空文件防护 |
| `src/skills/elevenlabs_tts.py` | +DEFAULT_VOICE_ID (Rachel), +voice_id参数 |
| `src/tools/gpt_image_client.py` | poyo优先 (POYO_API_KEY存在时) |
| `src/tools/translate.py` | NEW — 中文检测+LLM翻译+长度截断 |
| `src/tools/asset_storage.py` | +update_tags() |

## 前端改动

| 文件 | 改动概述 |
|------|---------|
| `web/src/app/page.tsx` | 4阶段状态机, +SceneTabs, +SceneForm, +RecommendPanel, +GatePanel, +StageProgress, +CompareView, +Smart Create路由, +localStorage Expert恢复, +mode默认expert |
| `web/src/app/layout.tsx` | +I18nProvider 包裹 |
| `web/src/app/brand-packages/page.tsx` | NEW — 品牌资产CRUD页面(双语) |
| `web/src/app/influencers/page.tsx` | NEW — 网红管理CRUD页面(双语) |
| `web/src/app/footage/page.tsx` | NEW — 素材上传管理页面(双语) |
| `web/src/components/SceneTabs.tsx` | NEW — 3场景tab入口 |
| `web/src/components/SceneForm.tsx` | NEW — 独立表单(S1/S2/S3各不同), +Product Details段, +Brand Voice段 |
| `web/src/components/RecommendPanel.tsx` | NEW — AI推荐面板(时长+平台+策略摘要+模式切换), +防双击guard |
| `web/src/components/GatePanel.tsx` | NEW — Gate审批通用框架 |
| `web/src/components/CandidateSelector.tsx` | NEW — 3候选对比卡片 |
| `web/src/components/StageProgress.tsx` | NEW — 3阶段进度条 |
| `web/src/components/CompareView.tsx` | NEW — Gate4双版本对比 |
| `web/src/components/DurationSlider.tsx` | 滑动条→5档区间按钮, +i18n |
| `web/src/components/StepByStepView.tsx` | +Gate暂停点, +i18n |
| `web/src/components/OneShotResultView.tsx` | -冗余时长徽标, +i18n |
| `web/src/components/QualityDashboard.tsx` | +i18n |
| `web/src/components/Nav.tsx` | +中/EN切换按钮, +i18n |
| `web/src/components/SceneSelector.tsx` | +PLATFORM_LABELS导入修复, -S4移除, +i18n |
| `web/src/components/api.ts` | 错误消息英文化, +video_duration类型 |
| `web/src/components/types.ts` | -S4移除, PLATFORM_LABELS英文化 |
| `web/src/i18n/translations.ts` | 1000+行, 200+键, zh/en双语 |
| `web/src/i18n/I18nProvider.tsx` | NEW — React Context, useI18n hook |

## 文档新增

| 文件 | 内容 |
|------|------|
| `docs/spike/2026-04-28_image2-seedance-optimization-plan.md` | Image2+Seedance质量优化计划 |
| `docs/spike/2026-04-28_integrated-master-plan.md` | 四文档一致性整合总计划 |
| `docs/spike/2026-04-28_pre-test-checklist.md` | 17项预测试检查清单 |
| `docs/spike/2026-04-28_delivery-summary.md` | 35项交付总结 |
| `docs/spike/2026-04-28_product-deep-dive.md` | 产品深度剖析(反直觉洞察) |
| `docs/spike/2026-04-28_product-deep-dive-v2.md` | 产品讨论v2(三场景入口+双模式+审批节点) |
| `docs/spike/2026-04-29_execution-plan-v3.md` | 分层可执行计划v3 |
| `docs/spike/2026-04-29_pipeline-execution-deep-dive.md` | 12步管线深度执行分析 |
| `docs/spike/2026-04-29_strategy-quality-guide.md` | 策略质量提升指南 |
| `docs/spike/2026-04-29_changelog.md` | 本文 — 改动记录 |
| `docs/reference/api-endpoints.md` | 44端点API参考文档 |
| `docs/guide/quick-start.md` | 快速入门指南 |
| `.env.example` | 环境变量模板 |

---

## 场景差异识别的待处理问题

### S2 品牌宣传 — 策略步骤未适配

S2 走 S1 的 pipeline（brand_mode=True），strategy 步骤使用同一个 `product_strategy.py` 和同一个 system prompt。但 S2 的输入是 `brand_package`（品牌资产包），而非 `product_catalog`（产品信息）。strategy prompt 中的 "Product Context" 段对 S2 不适用——没有 pain_points、没有 competitor_context。

**待处理：** S2 需要独立的 strategy prompt 段，或至少在 brand_mode=True 时动态切换 Product Context 段为 Brand Campaign Context 段。

### S3 网红二创 — 不走 strategy 步骤

S3 管线不调用 `product-to-video-strategy`，而是调用 `video-analysis` → `character-identity` → `remix-script`。所以 strategy prompt 的改进对 S3 无效。

**待处理：** S3 的质量取决于 `video_analysis.py` 和 `remix_script.py` 的 LLM 调用。这两个 skill 有类似问题——信息贫乏。video_analysis 只看原视频的转录文本，remix_script 只看 analysis 结果+产品信息。它们都没有产品上下文（pain_points、target_audience 等）。

### S3 的关键帧和连续性链

S3 已集成 character_identity 和 keyframe_images，但这两步的质量取决于原视频的人脸质量和 GPT-Image 的生成稳定性——这两者都不可控。

---

## 综合评估

| 场景 | 策略质量 | 脚本质量 | 视觉质量 | 整体 |
|------|---------|---------|---------|------|
| S1 商品直拍 | ✅ 已增强(上下文+规则) | ✅ 已并行化 | ⚠️ 依赖 Seedance API | 🟢 可测试 |
| S2 品牌宣传 | ⚠️ prompt 未区分 S2 | ✅ 同上 | ⚠️ 同上 | 🟡 需 prompt 适配 |
| S3 网红二创 | ⚠️ 不同 skill，未优化 | ⚠️ remix_script 缺上下文 | ⚠️ 人脸一致性不可控 | 🟡 需多维度优化 |
