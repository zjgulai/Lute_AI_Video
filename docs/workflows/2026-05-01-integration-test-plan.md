---
title: AI Video Pipeline 前后端深度联调测试计划
doc_type: workflow
module: testing
status: draft
created: 2026-05-01
updated: 2026-05-01
owner: self
source: human+ai
---

# AI Video Pipeline 前后端深度联调测试计划

**版本**: v1.0 · **日期**: 2026-05-01
**目标**: 部署前全面体检，确保所有前后端交互节点可靠、可观测、可定位

---

## 一、测试总览

### 1.1 架构速览

```
┌─────────────────────────────────────────────────────────────────┐
│                         用户浏览器                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │  Next.js 15 │  │  React 19   │  │  Zustand Stores         │ │
│  │  (Port 3000)│  │  UI 2.0     │  │  useApp/usePipeline/    │ │
│  └──────┬──────┘  └─────────────┘  │  useExpert              │ │
│         │                           └─────────────────────────┘ │
│         │ api.ts: 26 functions                                    │
│         ▼                                                       │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  [LOG] Frontend Request/Response Interceptor              │  │
│  │  trace_id | method | path | status | duration | payload   │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────┬───────────────────────────────────────────────────────┘
          │ HTTPS (Nginx 443)
          ▼
┌─────────────────────────────────────────────────────────────────┐
│  Nginx (Port 80/443)                                            │
│  ├─ /health      → backend:8001/health                          │
│  ├─ /api/media/  → backend:8001/api/media/ (保留前缀)            │
│  ├─ /api/assets/ → backend:8001/api/assets/ (保留前缀)           │
│  ├─ /api/files   → backend:8001/api/files                       │
│  ├─ /api/upload  → backend:8001/api/upload                      │
│  ├─ /api/*       → backend:8001/ (strip /api)                   │
│  └─ /*           → frontend:3000                                 │
└─────────┬───────────────────────────────────────────────────────┘
          │ HTTP (Docker Network)
          ▼
┌─────────────────────────────────────────────────────────────────┐
│  FastAPI (Port 8001)                                            │
│  ├─ [Middleware] CORS → RateLimit → RequestLog                  │
│  ├─ [Middleware] ResponseWrapper (trace_id, duration, version)  │
│  ├─ [Router] health    — /health (no auth)                      │
│  ├─ [Router] pipeline  — /pipeline/* (LangGraph)                │
│  ├─ [Router] scenario  — /scenario/* (S1-S5 + FastMode)         │
│  ├─ [Router] assets    — /api/assets/*                          │
│  ├─ [Router] media     — /api/media/* (no auth)                 │
│  ├─ [Router] distribution — /distribution/*                     │
│  ├─ [Router] metrics   — /metrics/*                             │
│  └─ [Router] telemetry — /telemetry/*                           │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 测试范围

| 层级 | 测试内容 | 优先级 |
|------|---------|--------|
| L1 连接层 | Health, CORS, API Key, Rate Limit, Demo Key 限制 | P0 |
| L2 场景管道 | S1-S5 完整数据流, Fast Mode, Step-by-step | P0 |
| L3 专家工作室 | Gate 审核, 步骤编辑, 状态恢复 | P0 |
| L4 媒体服务 | 上传, 下载, 签名 URL, 跨域 | P1 |
| L5 发布分发 | 平台发布, 状态查询, 指标看板 | P1 |
| L6 UI 2.0 新功能 | GuidedForm, DirectorPlayback, InsightReport | P1 |
| L7 边界恢复 | 断网, 超时, 并发, 大文件, 模式切换 | P2 |
| L8 性能 | 轮询频率, 内存泄漏, 响应时间 | P2 |

### 1.3 日志设计规范

**前端 console 输出格式**:
```
[HERMES:REQ] POST /scenario/s1 {product_catalog: {...}} trace_id=abc123
[HERMES:RES] 200 OK (2345ms) trace_id=abc123 {success: true, label: "s1_..."}
[HERMES:ERR] 500 Internal Server Error (120ms) trace_id=def456
[HERMES:POOL] GET /scenario/s1/state/label (500ms) step=strategy status=done
```

**后端响应包装格式**:
```json
{
  "data": { ...original_response... },
  "_meta": {
    "trace_id": "abc123",
    "duration_ms": 2345,
    "version": "0.2.0",
    "timestamp": "2026-05-01T12:00:00Z"
  }
}
```

---

## 二、L1 连接层测试 (P0)

### 2.1 Health Check

| # | 测试项 | 预期结果 | Console 查看 |
|---|-------|---------|-------------|
| L1-1 | GET /health | 200, status=ok, version=0.2.0 | `console.log` → `[HERMES:HEALTH] ok` |
| L1-2 | Health 返回 persistence 状态 | pg_available 布尔值 | 确认 DB 连接状态 |
| L1-3 | Health 返回 remotion 状态 | validate_environment 结果 | 确认渲染服务可用 |

### 2.2 CORS 测试

| # | 测试项 | 预期结果 | Console 查看 |
|---|-------|---------|-------------|
| L1-4 | 前端请求带 Origin | 响应头含 Access-Control-Allow-Origin | Network Tab |
| L1-5 | Preflight OPTIONS | 204, 允许 method/header | Network Tab |
| L1-6 | 跨域 API Key header | X-API-Key 在 allow_headers 中 | 请求不报错 |

### 2.3 API Key 认证

| # | 测试项 | 预期结果 | Console 查看 |
|---|-------|---------|-------------|
| L1-7 | 无 API Key | 401 Unauthorized | `[HERMES:ERR] 401` |
| L1-8 | 错误 API Key | 401 Invalid API key | `[HERMES:ERR] 401` |
| L1-9 | 正确 API Key | 正常访问 | `[HERMES:RES] 200` |
| L1-10 | Demo Key DELETE 请求 | 403 Demo key cannot delete | `[HERMES:ERR] 403` |
| L1-11 | Demo Key publish | 403 Demo key cannot publish | `[HERMES:ERR] 403` |
| L1-12 | Demo Key asset upload | 403 Demo key cannot modify assets | `[HERMES:ERR] 403` |

### 2.4 速率限制

| # | 测试项 | 预期结果 | Console 查看 |
|---|-------|---------|-------------|
| L1-13 | 120 req/min 内 | 正常响应 | 无异常 |
| L1-14 | 超过 120 req/min | 429 Too Many Requests | `[HERMES:ERR] 429` |
| L1-15 | Health 不计入限流 | 不受限 | 验证 |

---

## 三、L2 场景管道测试 (P0)

### 3.1 S1 Product Direct (Smart Create)

**前端调用链**:
```
page.tsx:startSmartCreate()
  → api.ts:runS1ProductDirect()
    → POST /scenario/s1
      → scenario.py:run_s1_product_direct()
        → StepRunner.init_state() → StepRunner.resume()
          → 各步骤执行 (strategy → scripts → storyboards → ... → assemble_final)
    ← 返回完整 result
  ← page.tsx 显示 OneShotResultView
```

| # | 测试项 | 预期结果 | Console 查看 |
|---|-------|---------|-------------|
| S1-1 | 正常产品参数 | 200, success=true, 含 briefs/scripts/clip_paths | `[HERMES:RES] 200` 含完整字段 |
| S1-2 | 中文产品名 | 自动翻译为英文, _original_zh 保留 | 确认 translation 执行 |
| S1-3 | 无 product_catalog | 500 或空数组处理 | `[HERMES:ERR]` 含 trace_id |
| S1-4 | 超长 video_duration | 边界值 15/30/45/60/90 | 确认后端裁剪逻辑 |
| S1-5 | 返回字段完整性 | 含 final_video_path, audit_report, thumbnail_image_paths | 验证所有字段存在 |
| S1-6 | StepRunner fallback | structlog 失败时回退 S1ProductDirectPipeline | 日志含 fallback 信息 |

**关键字段验证清单**:
```javascript
result.success === true
result.briefs.length > 0
result.scripts.length > 0
result.clip_paths.length > 0
result.final_video_path !== undefined
result.audit_report.overall_score > 0
result.audit_report.criteria.length > 0
```

### 3.2 S2 Brand Campaign

| # | 测试项 | 预期结果 | Console 查看 |
|---|-------|---------|-------------|
| S2-1 | 正常品牌包 | 200, 含多渠道内容 | `[HERMES:RES] 200` |
| S2-2 | 空 brand_package | 500 或优雅降级 | `[HERMES:ERR]` |
| S2-3 | target_platforms 边界 | ["tiktok"] / ["shopify"] / 多平台 | 确认适配 |

### 3.3 S3 Influencer Remix

| # | 测试项 | 预期结果 | Console 查看 |
|---|-------|---------|-------------|
| S3-1 | 正常视频 URL | 200, 含 remix 内容 | `[HERMES:RES] 200` |
| S3-2 | 无效视频 URL | 500 或错误提示 | `[HERMES:ERR]` |
| S3-3 | 中文 product 翻译 | _original_zh 保留 | 确认翻译 |

### 3.4 S4 Live Shoot

| # | 测试项 | 预期结果 | Console 查看 |
|---|-------|---------|-------------|
| S4-1 | 正常素材数组 | 200, 含剪辑内容 | `[HERMES:RES] 200` |
| S4-2 | 空 footage_assets | 500 或空结果 | `[HERMES:ERR]` |

### 3.5 S5 Brand VLOG

| # | 测试项 | 预期结果 | Console 查看 |
|---|-------|---------|-------------|
| S5-1 | 正常参数 | 200, 含视频路径 | `[HERMES:RES] 200` |
| S5-2 | 六视图 product_sku | 正确解析 views[] | 确认字段映射 |
| S5-3 | scene_id 边界 | office/living-room/bedroom 等 | 确认场景有效 |

### 3.6 Fast Mode

| # | 测试项 | 预期结果 | Console 查看 |
|---|-------|---------|-------------|
| F-1 | 正常 prompt | 200, 10s/15s 视频 | `[HERMES:RES] 200` |
| F-2 | enable_tts=true | 含 tts_path | 确认音频生成 |
| F-3 | 超长 prompt | 正常截断或处理 | 确认不崩溃 |
| F-4 | duration 边界 | <10 → 10, >15 → 15 | 确认裁剪 |
| F-5 | 返回字段 | success/video_path/timing/model_info | 验证所有字段 |

---

## 四、L3 Expert Studio (Step-by-Step) 测试 (P0)

### 4.1 Step-by-Step 初始化

```
page.tsx:handleStart() (mode=step_by_step)
  → api.ts:startS1StepByStep()
    → POST /scenario/s1/start
      → scenario.py:start_s1_pipeline()
        → StepRunner.init_state()
    ← { label, mode, status: "initialized" }
```

| # | 测试项 | 预期结果 | Console 查看 |
|---|-------|---------|-------------|
| E1-1 | 正常初始化 | 200, label 生成 | `[HERMES:RES] 200` 含 label |
| E1-2 | mode=auto | 直接返回最终状态 | 无中间状态 |
| E1-3 | mode=step_by_step | status="initialized" | 等待 resume |

### 4.2 单步执行

```
StepByStepView
  → api.ts:runS1Step()
    → POST /scenario/s1/step/{step_name}
      → scenario.py:run_s1_step()
        → StepRunner.run_step()
    ← { step, status, data }
```

| # | 测试项 | 预期结果 | Console 查看 |
|---|-------|---------|-------------|
| E2-1 | 执行 strategy | 200, status="done" | `[HERMES:RES] 200` |
| E2-2 | 跳过依赖步骤 | 400, missing_deps | `[HERMES:ERR] 400` |
| E2-3 | 重复执行已完成步骤 | 200, cached=true | `[HERMES:RES] 200 cached` |
| E2-4 | 编辑后重新生成 | invalidate_downstream 生效 | 下游状态重置 |

### 4.3 Gate 审核

```
GatePanel
  → api.ts:generateGateCandidates() (前端无此函数, 需确认调用方式)
    → POST /scenario/s1/gate/{label}/{gate_id}/generate
  → api.ts:approveGateDecision() (前端无此函数)
    → POST /scenario/s1/gate/{label}/{gate_id}/approve
```

| # | 测试项 | 预期结果 | Console 查看 |
|---|-------|---------|-------------|
| G1-1 | 生成候选 | 3 variants (standard/creative/conservative) | 确认候选数组 |
| G1-2 | 审核通过 | 200, resumed=true, background_task_id | `[HERMES:RES] 200` |
| G1-3 | 重复审核 | 409 Already approved | `[HERMES:ERR] 409` |
| G1-4 | 背景 resume | 5-30分钟后完成 | 轮询状态更新 |

### 4.4 状态管理

```
page.tsx 轮询
  → api.ts:fetchS1State()
    → GET /scenario/s1/state/{label}
  → api.ts:fetchS1StepList()
    → GET /scenario/{scenario}/state/{label}/steps
```

| # | 测试项 | 预期结果 | Console 查看 |
|---|-------|---------|-------------|
| SM-1 | 状态加载 | 含 steps 各步骤状态 | `[HERMES:POOL] status` |
| SM-2 | 步骤列表 | 含 preview/has_output/is_edited | 确认字段 |
| SM-3 | 状态更新 (PUT) | 深度合并生效 | `[HERMES:RES] 200` |
| SM-4 | 状态持久化 | 重启后 label 可加载 | 确认磁盘存储 |

---

## 五、L4 媒体服务测试 (P1)

### 5.1 媒体获取

```
前端: getMediaUrl(filePath)
  → /api/media/{encoded_path}
    → media.py
      → 文件系统读取
```

| # | 测试项 | 预期结果 | Console 查看 |
|---|-------|---------|-------------|
| M1-1 | 正常视频获取 | 200, Content-Type: video/mp4 | Network Tab |
| M1-2 | 正常图片获取 | 200, Content-Type: image/* | Network Tab |
| M1-3 | 路径含中文 | 正确 encode/decode | URL 编码正确 |
| M1-4 | 文件不存在 | 404 | `[HERMES:ERR] 404` |
| M1-5 | 签名 URL | GET /api/media/sign?path= | 返回临时 URL |

### 5.2 资产上传

```
footage/page.tsx
  → POST /api/assets/upload (FormData)
    → assets.py
```

| # | 测试项 | 预期结果 | Console 查看 |
|---|-------|---------|-------------|
| M2-1 | 上传图片 | 200, asset_id 返回 | `[HERMES:RES] 200` |
| M2-2 | 上传视频 | 200, 文件大小正确 | `[HERMES:RES] 200` |
| M2-3 | 大文件 (>100MB) | 413 或分片处理 | `[HERMES:ERR] 413` |
| M2-4 | 不支持的格式 | 400 或 415 | `[HERMES:ERR]` |
| M2-5 | Demo key 上传 | 403 | `[HERMES:ERR] 403` |

### 5.3 资产列表

```
footage/page.tsx / brand-packages/page.tsx
  → GET /api/assets/ 或 GET /api/files
    → assets.py / api_assets.py
```

| # | 测试项 | 预期结果 | Console 查看 |
|---|-------|---------|-------------|
| M3-1 | 列表获取 | 200, files[] 数组 | `[HERMES:RES] 200` |
| M3-2 | 标签过滤 | ?tags=footage | 过滤生效 |
| M3-3 | Demo 模式 | 返回 DEMO_FOOTAGE_ASSETS | 确认 mock 数据 |

---

## 六、L5 发布分发测试 (P1)

### 6.1 平台列表

| # | 测试项 | 预期结果 | Console 查看 |
|---|-------|---------|-------------|
| D1-1 | GET /distribution/platforms | 平台列表 | `[HERMES:RES] 200` |

### 6.2 发布内容

```
OneShotResultView → PlatformPublishRow
  → api.ts:publishContent()
    → POST /distribution/publish
```

| # | 测试项 | 预期结果 | Console 查看 |
|---|-------|---------|-------------|
| D2-1 | 正常发布 | 200, post_id | `[HERMES:RES] 200` |
| D2-2 | Demo key | 403 | `[HERMES:ERR] 403` |
| D2-3 | 无效 platform | 400 或 404 | `[HERMES:ERR]` |

### 6.3 视频发布

```
PublishPanel / PublishFlow
  → api.ts:publishVideo()
    → POST /publish/{video_id}
```

| # | 测试项 | 预期结果 | Console 查看 |
|---|-------|---------|-------------|
| D3-1 | 正常发布 | 200, 多平台结果 | `[HERMES:RES] 200` |
| D3-2 | 部分失败 | 结果含 success/error 混合 | 确认错误平台 |

### 6.4 指标看板

| # | 测试项 | 预期结果 | Console 查看 |
|---|-------|---------|-------------|
| D4-1 | GET /dashboard/overview | 统计数据 | `[HERMES:RES] 200` |
| D4-2 | GET /metrics/{video_id} | 视频指标 | `[HERMES:RES] 200` |

---

## 七、L6 UI 2.0 新功能测试 (P1)

### 7.1 GuidedForm → Smart Create

```
SceneForm → GuidedForm → onSubmit
  → page.tsx:startSmartCreate()
    → 同 L2 S1 流程
```

| # | 测试项 | 预期结果 | Console 查看 |
|---|-------|---------|-------------|
| U1-1 | 品牌 VLOG 场景 | 正确收集卡片数据 | `[HERMES:REQ] /scenario/s5` |
| U1-2 | 模板选择 | QuickTemplate 回填字段 | 确认 values 传递 |
| U1-3 | Live Summary | 实时更新完成度 | 状态正确同步 |
| U1-4 | 必填校验 | 未填完禁止提交 | 按钮 disabled |

### 7.2 DirectorPlayback → 结果展示

```
OneShotResultView → DirectorPlayback
  → 展示 video/script/storyboards/audit/publish/insight/download
```

| # | 测试项 | 预期结果 | Console 查看 |
|---|-------|---------|-------------|
| U2-1 | 视频播放 | getMediaUrl 返回正确 | 视频加载成功 |
| U2-2 | 脚本折叠展开 | PlaybackSection 切换 | 状态正确 |
| U2-3 | 质量报告 | audit_report 渲染 | 分数/状态正确 |
| U2-4 | 经典视图切换 | viewMode="classic" | Tab 正常渲染 |

### 7.3 PublishFlow → 发布

```
DirectorPlayback → PublishFlow
  → 自动填充 metadata → 平台选择 → 发布
```

| # | 测试项 | 预期结果 | Console 查看 |
|---|-------|---------|-------------|
| U3-1 | 自动填充 | briefs[0] + scripts[0] 提取 | 字段正确 |
| U3-2 | 平台选择 | 点击切换选中态 | UI 正确 |
| U3-3 | 发布后状态 | 静默替换为确认文字 | 按钮消失 |

### 7.4 InsightReport → 数据复盘

```
DirectorPlayback → InsightReport
  → 按 videoType 展示北极星指标
```

| # | 测试项 | 预期结果 | Console 查看 |
|---|-------|---------|-------------|
| U4-1 | 品牌形象片 | 显示 watchRate + followerGrowth | 无 ROI 树 |
| U4-2 | 产品种草 | 显示 ROI 分解树 | 含 views→ctr→cvr→sales |
| U4-3 | AI 总结 | 纯前端生成 | 文本正确 |

### 7.5 GalleryGrid → 创作画廊

```
footage/page.tsx → GalleryGrid
  → localStorage "hermes_gallery_items"
```

| # | 测试项 | 预期结果 | Console 查看 |
|---|-------|---------|-------------|
| U5-1 | 作品保存 | page.tsx:saveToGallery 执行 | localStorage 写入 |
| U5-2 | 场景分组 | grouped by scene | 分组正确 |
| U5-3 | Tab 切换 | 成品/素材切换 | 内容正确 |

### 7.6 AssetCard → 品牌资产

```
brand-packages/page.tsx → AssetCard
  → 来源筛选 + 分类导航
```

| # | 测试项 | 预期结果 | Console 查看 |
|---|-------|---------|-------------|
| U6-1 | 分类过滤 | 左导航树过滤 | 数量正确 |
| U6-2 | 来源筛选 | AI/人工/导入 | 过滤生效 |
| U6-3 | 搜索 | 标题/内容搜索 | 结果正确 |

---

## 八、L7 错误恢复 + 边界条件 (P2)

### 8.1 网络中断

| # | 测试项 | 预期结果 | Console 查看 |
|---|-------|---------|-------------|
| R1-1 | 请求中断断网 | TypeError: Failed to fetch | `[HERMES:ERR] Network` |
| R1-2 | 轮询中断 | disconnected=true, 30s 间隔 | 状态正确 |
| R1-3 | 恢复后重连 | 自动恢复轮询 | 状态更新 |
| R1-4 | AbortController | 取消后无错误抛到 UI | 静默处理 |

### 8.2 后端超时

| # | 测试项 | 预期结果 | Console 查看 |
|---|-------|---------|-------------|
| R2-1 | Nginx 300s 超时 | 504 Gateway Timeout | `[HERMES:ERR] 504` |
| R2-2 | 后台任务 (Gate resume) | background_task_id 返回 | 异步处理 |
| R2-3 | 前端超时处理 | 显示超时提示 | UI 提示正确 |

### 8.3 Demo 模式切换

| # | 测试项 | 预期结果 | Console 查看 |
|---|-------|---------|-------------|
| R3-1 | hostname 判断 | github.io / vercel.app → demo | isDemoMode() 正确 |
| R3-2 | localStorage 覆盖 | ai_video_demo_mode=true | 优先级正确 |
| R3-3 | Demo 模式 API 调用 | 返回 mock 数据 | 无网络请求 |

### 8.4 并发请求

| # | 测试项 | 预期结果 | Console 查看 |
|---|-------|---------|-------------|
| R4-1 | 同时发起 2 个 pipeline | 第 2 个排队或拒绝 | Semaphore 生效 |
| R4-2 | 快速切换场景 | 旧请求取消 | AbortController 生效 |

---

## 九、L8 性能测试 (P2)

### 9.1 响应时间基准

| # | 测试项 | 预期基准 | Console 查看 |
|---|-------|---------|-------------|
| P1-1 | /health | <100ms | `[HERMES:RES] (XXms)` |
| P1-2 | /scenario/s1 (FastMode) | <30s | 总耗时 |
| P1-3 | /scenario/s1 (auto) | <5min | 总耗时 |
| P1-4 | /scenario/s1/state/{label} | <500ms | 轮询耗时 |
| P1-5 | /api/media/ | 视频 <2s, 图片 <500ms | 加载时间 |

### 9.2 轮询优化

| # | 测试项 | 预期行为 | Console 查看 |
|---|-------|---------|-------------|
| P2-1 | 活跃状态 | 3s 间隔 | 请求频率 |
| P2-2 | 完成状态 | 10s 间隔 | 请求频率 |
| P2-3 | 断网状态 | 30s 间隔 | 请求频率 |

### 9.3 内存泄漏

| # | 测试项 | 预期行为 | Console 查看 |
|---|-------|---------|-------------|
| P3-1 | 长时间轮询 | setInterval 正确清理 | 无重复轮询 |
| P3-2 | 组件卸载 | AbortController 取消 | 无悬空请求 |
| P3-3 | 线程缓存 | _cleanup_thread_cache 生效 | 内存稳定 |

---

## 十、测试执行清单

### 前置条件
- [ ] 后端启动: `uvicorn src.api:app --reload --port 8001`
- [ ] 前端启动: `cd web && npm run dev`
- [ ] 浏览器打开: `http://localhost:3000`
- [ ] Console 过滤: `[HERMES`

### 执行顺序
1. L1 连接层 (基础必须先过)
2. L2 场景管道 (核心功能)
3. L3 Expert Studio (复杂流程)
4. L4 媒体服务 (文件处理)
5. L5 发布分发 (可选功能)
6. L6 UI 2.0 (新功能回归)
7. L7 边界恢复 (稳定性)
8. L8 性能 (基准)

### 结果记录格式
```
[PASS] L1-1 Health Check — 200 OK, version=0.2.0, pg_available=true
[FAIL] S1-3 无 product_catalog — 500, trace=abc123, 期望: 优雅降级
[SKIP] D2-1 发布测试 — 无平台 API Key
```

---

## 十一、待修复问题追踪

| ID | 问题描述 | 发现位置 | 严重程度 | 状态 |
|----|---------|---------|---------|------|
| | | | | |
