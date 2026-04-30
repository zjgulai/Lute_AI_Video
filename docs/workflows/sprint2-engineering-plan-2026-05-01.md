---
title: Sprint 2 工程化重构实施计划
doc_type: workflow
module: project-governance
topic: sprint2-plan
status: stable
created: 2026-05-01
updated: 2026-05-01
owner: self
source: ai+human
---

# Sprint 2 工程化重构实施计划

## 范围

6 个大工程项，预估总工期 **11-16 天**（单人全速）。

| 编号 | 任务 | 预估 | 依赖 |
|------|------|------|------|
| P2-9 | Alembic 数据库迁移管理 | 1 天 | 无 |
| P2-7 | 前后端类型同步（OpenAPI → TS） | 1 天 | 无 |
| P2-6 | 前端测试配置（Vitest + RTL） | 1 天 | 无 |
| P1-11 | api.py 1800+ 行按领域拆分 router | 3-5 天 | 无 |
| P1-13 | Zustand 全局状态管理 | 2-3 天 | 无 |
| P1-12 | 前端 page.tsx 路由拆分 | 3-5 天 | 依赖 P1-13 |

## Phase 1：基础设施（1-2 天）

三项互相独立，可并行。

### P2-9 Alembic 迁移

当前 `src/storage/migrations/` 目录已存在，需确认现有方案并统一为 Alembic。

**验收**：新表/改表必须通过 Alembic migration，禁止手写 ALTER。

### P2-7 类型同步

后端 FastAPI 自动生成 OpenAPI schema → `openapi-typescript` 生成 TS 类型。

**验收**：前端不再使用 `any` 传递 API 响应数据。

### P2-6 前端测试

配置 Vitest + React Testing Library，为 2-3 个核心组件补测试。

**验收**：`pnpm test` 能运行，至少 3 个组件有单元测试。

## Phase 2：后端架构（3-5 天）

### P1-11 api.py 拆分

按领域拆分为独立 router 模块：

```
src/routers/
├── __init__.py
├── pipeline.py      # /pipeline/* (5 端点)
├── scenario.py      # /scenario/* + /fast/* (15 端点)
├── distribution.py  # /distribution/* + /publish/* (4 端点)
├── metrics.py       # /metrics/* + /dashboard/* (3 端点)
├── assets.py        # /api/upload, /api/files (2 端点)
├── media.py         # /api/media/*, /api/media/sign (2 端点)
└── health.py        # /health (1 端点)
```

**共享 helper 提取到 `src/routers/_deps.py`**：
- `verify_api_key`
- `_get_config_for_thread`
- `_touch_thread_cache`
- `_cleanup_thread_cache`
- `_safe_error`
- `_serialize`

**验收**：
- 所有现有端点正常工作
- `src/api.py` 只保留 app 创建、middleware、router 挂载

## Phase 3：前端架构（5-8 天）

### P1-13 Zustand 全局状态

提取 page.tsx 中 31 个 useState 为 Zustand store：

```
web/src/stores/
├── useAppStore.ts      # stage, mode, activeScene, toast
├── usePipelineStore.ts # threadId, workflowLabel, workflowState
├── useExpertStore.ts   # currentGate, showCompare
└── useUIStore.ts       # showSettings, showAssetLibrary, loading
```

**验收**：
- page.tsx useState 数量从 31 降到 < 10
- 跨组件状态不再 props drilling

### P1-12 路由拆分

按场景拆分为独立页面：

```
web/src/app/
├── page.tsx              # 首页（场景选择）
├── layout.tsx            # 根布局（Nav + ErrorBoundary）
├── s1/
│   └── page.tsx          # Product Direct（原 expert/smart 模式）
├── s2/
│   └── page.tsx          # Brand Campaign
├── s3/
│   └── page.tsx          # Influencer Remix
├── s4/
│   └── page.tsx          # Live Shoot
├── s5/
│   └── page.tsx          # Brand Vlog
├── fast/
│   └── page.tsx          # Fast Mode
├── result/
│   └── page.tsx          # OneShotResultView
└── settings/
    └── page.tsx          # SettingsPanel 独立页面
```

**验收**：
- URL 能反映当前场景（如 `/s1?mode=expert`）
- 浏览器前进/后退正常工作

## 执行策略

1. **每完成一个 Phase 就提交一次**，不积压
2. **拆分前先备份**：`git branch sprint2-backup`
3. **每迁移一个 router 就测试一组端点**
4. **Zustand 和路由拆分可渐进**：先提取最混乱的状态（workflow 相关），再逐步替换

## 风险

| 风险 | 缓解 |
|------|------|
| api.py 拆分破坏现有端点 | 逐个 router 迁移，每迁移完一组就 curl 测试 |
| Zustand 引入后状态同步 bug | 保留现有 props 作为 fallback，渐进替换 |
| 路由拆分后状态丢失 | URL query params 持久化关键状态 |
