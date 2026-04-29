# AI_Vedio Multi-Scenario Roadmap + Execution Plan

> 合并了两份 plan 的完整版：原始生产路线图 (R1-R10 架构演进) + 当前代码完成度全景图 + 下一步执行计划 (R9a/b/c)

---

## 第一部分：架构全景（原始设计 + 当前完成度）

### 整体架构

```
pipeline node -> SkillRegistry -> SkillCallable.execute(structured params)
                                      |
                              Skill internal: prompt template + retry + validation + fallback
```

每个 Skill 都是注册的独立模块。Pipeline 不做 LLM 调用，只调 Skill。

### 原始分层依赖图

```
Layer 0: 基础设施层 ──── R1+R2+R3 已完成 ✓
  I-1  Seedance 2.0 API client           (src/tools/seedance_client.py)
  I-2  gpt-image-2 API client            (src/tools/gpt_image_client.py)
  I-3  Video download + Whisper          (src/tools/video_downloader.py)
  I-4  Asset storage (local FS)          (src/tools/asset_storage.py)
  I-5  Product catalog CRUD              (src/tools/product_catalog.py)

Layer 1: Skill Engine ─── R3 已完成 ✓
  S-1  SkillCallable abstract base       (src/skills/base.py)
  S-2  SkillRegistry                     (src/skills/registry.py)
  S-3  LLMSkill inline implementation    (src/skills/llm_skill.py)

Layer 2: 内容生成 Skills ─── R4+R5+R7+R8 已完成 ✓
  S-4  product-to-video-strategy         (src/skills/product_strategy.py)
  S-5  brand-campaign-script             (src/skills/script_writer.py)
  S-6  influencer-remix-analysis         (src/skills/video_analysis.py)
  S-7  influencer-remix-script           (src/skills/remix_script.py)
  S-8  seedance-video-prompt             (src/skills/seedance_prompt.py)
  S-9  gpt-image-thumbnail-prompt        (src/skills/thumbnail_prompt.py)

Layer 3: 资产管理 ─── R6 已完成 ✓
  A-1  Asset upload API                  (src/api_assets.py)
  A-2  Asset tagging                     (src/tools/asset_storage.py)
  A-3  Brand asset package model + API   (src/models/brand.py + api_assets.py)
  A-4  Influencer profile management     (src/models/influencer.py + api_assets.py)

Layer 4: 审计 Skills ─── 部分完成
  S-10 brand-compliance-check            (src/skills/brand_compliance.py) ✓
  S-11 influencer-compliance-check       — 未实现
  S-12 viral-element-extractor           (src/skills/viral_extractor.py) ✓

Layer 5: 管道适配 ─── 部分完成
  P-1  E2E pipelines (S1-S4 pipelines)   (src/pipeline/s*.py) ✓ 4 pipelines
  P-2  16-node LangGraph全局图            (src/graph/pipeline.py) ✓ 原始12节点
  P-3  Scenario routing                  (state.py: content_scenario) ✓
  P-4  Retire mock_quality.py            — 未完成

Layer 6: E2E 测试 ─── 部分完成
  T-1  S1 Product Direct E2E            (tests/test_s1_e2e.py) ✓
  T-2  S2 Brand Campaign E2E            — 未实现
  T-3  S3 Influencer Remix E2E          (tests/test_s3_e2e.py) ✓
  T-4  S4 Live Shoot E2E                — 未实现
```

---

## 第二部分：完成度全景图

### 已完成（R1-R8）

| 轮次 | 交付物 | 文件数 | 测试数 | 状态 |
|------|--------|--------|--------|------|
| R1 | Seedance 客户端 + gpt-image-2 客户端 | 2 | 26 | ✓ |
| R2 | Video download/transcribe + AssetStorage | 2 | 37 | ✓ |
| R3 | Skill engine (base + registry + LLMSkill) + ProductCatalog | 4 | 43 | ✓ |
| R4 | Content gen skills (strategy, seedance prompt, thumbnail) | 3 | 38 | ✓ |
| R5 | S1 Product Direct E2E pipeline | 1 | 10 | ✓ |
| R6 | Asset system (upload API + brand/influencer models) | 5 | 32 | ✓ |
| R7 | Influencer remix skills (video analysis + remix script) | 2 | — | ✓ (内联在 R8) |
| R8 | S3 Influencer Remix E2E pipeline | 1 | 11 | ✓ |

**总计**: ~20 源文件, ~197 测试用例。

### 已完成的完整交付物清单

- **4 场景 Pipeline**: `s1_product_pipeline.py`, `s2_brand_pipeline.py`, `s3_remix_pipeline.py`, `s4_live_shoot_pipeline.py`
- **13 个注册 Skill**: video-analysis, remix-script, script-writer, storyboard, seedance-prompt, thumbnail-prompt, product-strategy, brand-compliance, viral-extractor, gpt-image-thumbnail-prompt, product-to-video-strategy, brand-compliance-skill, script-writer-skill
- **32 个测试文件**
- **Next.js 前端**: SceneSelector (4 场景 UI), PipelineMonitor, ReviewPanel, DistributionView
- **Asset API**: upload/get/list/delete, brand-packages CRUD, influencers CRUD
- **策略配置**: `strategy_source/` 加载器 + general + influencer_remix 配置
- **策略配置全覆盖**: `strategy_source/product_direct/`, `strategy_source/brand_campaign/`, `strategy_source/live_shoot_to_video/`（R9a-2 已补全后）

### 关键缺口

| # | 缺口 | 影响 | 优先级 |
|---|------|------|--------|
| G1 | 无持久化存储（全内存 dict） | 重启丢数据，无法多人协作 | P0 |
| G2 | S4 素材分析薄弱（无 scene detection） | Live-shoot 场景质量差 | P0 |
| G3 | 策略配置不完整（缺 brand_campaign / live_shoot） | 这俩场景没有差异化配置 | P0 |
| G4 | 无 trace_id / 结构化错误收集 | 出问题只能 ssh 看日志 | P1 |
| G5 | 网红/品牌/素材无 Web 管理界面 | 业务人员无法操作 | P1 |
| G6 | 无真实分发（只有 post 内容生成） | 生成的内容发不出去 | P1 |
| G7 | 无认证/限流 | 不能给客户用 | P2 |

---

## 第三部分：执行计划（R9a/b/c）

### 执行优先级矩阵

```
⭐ 评分规则：紧急度(P0=5,P1=3,P2=1) x 业务价值(高=5,中=3,小=1) / 工作量(小=3,中=2,大=1)
              = 效率分（越高越优先做）
```

| 排名 | 项 | 紧急度 | 价值 | 工作量 | 效率分 | 类型 |
|------|----|--------|------|--------|--------|------|
| ⭐1 | R9a-2 策略全覆盖 | P0(5) | 高(5) | 小(3) | 8.3 | 配置 |
| ⭐2 | R9a-1 PG 持久化 | P0(5) | 高(5) | 中(2) | 5.0 | 基础设施 |
| ⭐3 | R9a-3 S4 素材增强 | P0(5) | 高(5) | 中(2) | 5.0 | 功能 |
| ⭐4 | R9b-2 品牌资产 UI | P1(3) | 中(3) | 小(3) | 3.0 | Web UI |
| ⭐5 | R9b-3 素材上传 UI | P1(3) | 高(5) | 小(3) | 5.0 | Web UI |
| ⭐6 | R9a-4 可观测性 | P1(3) | 高(5) | 中(2) | 3.0 | 基础设施 |
| ⭐7 | R9b-1 网红管理 UI | P1(3) | 高(5) | 中(2) | 3.0 | Web UI |
| ⭐8 | R9c-2 限流 | P2(1) | 中(3) | 小(3) | 1.0 | 加固 |
| ⭐9 | R9c-3 前端优化 | P2(1) | 中(3) | 小(3) | 1.0 | 加固 |
| ⭐10 | R9c-1 认证 | P2(1) | 中(3) | 中(2) | 0.6 | 加固 |
| ⭐11 | R9b-4 分发连接器 | P1(3) | 高(5) | 大(1) | 3.0 | 功能 |

### Phase R9a — 生产就绪缺口（P0 优先）⚡

#### R9a-1: 持久化存储（PostgreSQL 集成）

**现状**: 所有数据在 Python dict（`_active_threads`、`_brand_packages`、`_influencers`）
**后果**: 服务器重启 = 全部丢失。无法支撑多人使用
**工作量**: 中

执行：
1. `src/storage/` — 存储层目录
2. `src/storage/db.py` — asyncpg 连接池管理
3. `src/storage/models.py` — SQL schema（threads, brand_packages, influencers, assets → JSONB）
4. `src/storage/repository.py` — Repository pattern 包装 CRUD
5. 改造 `src/api.py` — PipelineStartRequest 写入 DB，fetch_state 从 DB 读
6. 改造 `src/api_assets.py` — 替换 dict 为 DB repository
7. 处理 `_serialize()` → 递归序列化 Pydantic 为 JSONB
8. 测试: `tests/test_storage.py`

#### R9a-2: 策略配置覆盖全部 4 场景

**现状**: `strategy_source/` 只有 general 和 influencer_remix
**工作量**: 小（纯配置文件）

执行：
1. `strategy_source/product_direct/` — 含 strategy_prompt.md, audit_weights.json, quality_thresholds.json, platform_config.json
2. `strategy_source/brand_campaign/` — 同上，调整 audit 权重（品牌合规更高）
3. `strategy_source/live_shoot_to_video/` — 同上，调整审计阈值（素材可用性权重更高）
4. 每个场景的 `strategy_prompt.md` 引用对应 `ContentScenario` 名称

#### R9a-3: S4 实拍素材管道增强

**现状**: S4 只做 footage 描述 → script → prompt，无素材分析
**工作量**: 中

执行：
1. `src/skills/footage_analyzer.py` — 分析上传素材（场景时长、质量评分、标签提取）
2. 增强 S4 pipeline：footage_analyzer step 替代原始列表遍历
3. `AssetStorage.search_by_tags()` 和 `analyze()` 方法
4. 测试: `tests/test_footage_analyzer.py`

#### R9a-4: 错误处理和可观测性

**现状**: 零散 structlog，无 trace_id
**工作量**: 中

执行：
1. `src/telemetry.py` 增强 — 请求级 trace_id
2. `src/graph/pipeline.py` — 全局 error handler（wrap all nodes）
3. `src/storage/metrics_repository.py` — pipeline run 指标写入

### Phase R9b — 业务功能 ⚡

#### R9b-1: 网红/员工管理系统增强

**现状**: API 有 CRUD 模型，无 Web 界面
**工作量**: 中

执行：
1. `web/src/app/influencers/` — CRUD 页面
2. API 批量导入（CSV）
3. 网红数据 ↔ Pipeline remix 时直接引用 profile

#### R9b-2: 品牌资产包 Web 管理

**现状**: API 有 CRUD，无前端
**工作量**: 小

执行：
1. `web/src/app/brand-packages/` — 创建/编辑品牌资产包
2. 连接品牌素材上传流程

#### R9b-3: 实拍素材上传 Web 界面

**现状**: API 有 upload 端点，无前端
**工作量**: 小

执行：
1. `web/src/app/footage/` — 拖拽上传、标签编辑、预览
2. 素材库浏览和搜索（`AssetStorage.search_by_tags()`）

#### R9b-4: Distribution 连接器

**现状**: DistributionView 前端组件有，无真实发布 API
**工作量**: 大

执行：
1. `src/connectors/tiktok_connector.py` — TikTok 发布 API
2. `src/connectors/shopify_connector.py` — Shopify 商品/博客 API
3. 定时发布调度（Celery beat）
4. 发布状态追踪

### Phase R9c — 生产加固

#### R9c-1: 认证与多租户

**现状**: 无认证
**工作量**: 中

1. JWT 中间件
2. API key 租户隔离
3. Web 登录页

#### R9c-2: 速率限制和配额

**现状**: 无限制
**工作量**: 小

1. Token bucket 限流
2. 租户级每日配额

#### R9c-3: 前端生产优化

**现状**: 开发模式
**工作量**: 小

1. Next.js build 优化
2. Docker 多阶段构建
3. Nginx + SSL

---

## 第四部分：文件变更清单

### 新建文件
```
src/storage/__init__.py            # NEW
src/storage/db.py                  # NEW - asyncpg 连接池
src/storage/models.py              # NEW - DB schema
src/storage/repository.py          # NEW - CRUD pattern
src/storage/metrics_repository.py  # NEW (R9a-4)
src/skills/footage_analyzer.py     # NEW (R9a-3)
src/connectors/__init__.py         # NEW (R9b-4)
src/connectors/tiktok_connector.py # NEW (R9b-4)
src/connectors/shopify_connector.py# NEW (R9b-4)
strategy_source/product_direct/    # NEW (R9a-2)
strategy_source/brand_campaign/    # NEW (R9a-2)
strategy_source/live_shoot_to_video/ # NEW (R9a-2)
web/src/app/influencers/           # NEW (R9b-1)
web/src/app/brand-packages/        # NEW (R9b-2)
web/src/app/footage/               # NEW (R9b-3)
tests/test_storage.py              # NEW
tests/test_footage_analyzer.py     # NEW
tests/test_connectors.py           # NEW
```

### 修改文件
```
src/api.py          # +DB 写入/读取 +trace_id
src/api_assets.py   # dict→DB 存储
src/graph/pipeline.py # +全局 error handler
src/telemetry.py    # +trace_id 支持
src/tools/asset_storage.py  # +search_by_tags() +analyze()
src/pipeline/s4_live_shoot_pipeline.py  # +footage analyzer step
```

---

## 第五部分：里程碑

| 里程碑 | 交付物 | 前置依赖 | 预计时间 |
|--------|--------|----------|---------|
| M1 | 策略配置覆盖 4 场景 | 无（纯配置文件） | 0.5 天 |
| M2 | PG 持久化 + 数据不丢 | 无 | 5 天 |
| M3 | S4 素材分析能力 | M2 | 2 天 |
| M4 | 可观测（trace + 结构化错误） | M2 | 2 天 |
| M5 | 品牌资产/素材/网红 Web 管理 | M2 | 4 天 |
| M6 | TikTok/Shopify 分发连接器 | M2 | 5 天 |
| M7 | 认证 + 限流 + 前端优化 | 所有 | 3 天 |

**总计约 21 天**（专注执行）

---

## 第六部分：风险

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| Seedance 2.0 国内不稳定 | 中 | 高 | 降级到 Kling 2.5；本地缓存结果 |
| 8+ Skill 串行调用延迟累计 | 高 | 中 | 后台批量处理；单视频串行先上线 |
| gpt-image-2 国内访问不了 | 中 | 高 | 降级到通义万相 / CogView / 本地 SD |
| 网红风格克隆质量不够 | 中 | 中 | 先只克隆语言风格，验证后再做视频克隆 |
| auditor.py → Skill 转换丢逻辑 | 低 | 高 | auditor.py 保留做 fallback，新技能在之上构建 |
| PG 部署在容器里需要管理 | 中 | 中 | 用 Docker Compose 管理 PG 容器；SQLite 做开发替代 |
