---
name: adr-005-poster-extraction-everywhere
description: ADR 005 — 把 video poster 抽取从单一 LangGraph webhook 钩子改成"每个生产端内联 + portfolio router backstop"的去中心化模型，消除 fast-mode / 直接 seedance / 直接 remotion 等旁路场景缺图问题。
doc_type: adr
module: portfolio
status: accepted
created: 2026-05-17
updated: 2026-05-17
owner: Sisyphus
source: ai
related:
  - file: ../../workflows/portfolio-ops-stable.md
    relation: implements
  - file: ../../runbooks/thumbnail-missing.md
    relation: incident-response
---

# ADR #005 — Poster Extraction at Every Video Producer

| | |
|---|---|
| 状态 | Accepted |
| 日期 | 2026-05-17 |
| 决策者 | 工程团队 |
| 影响 | `src/skills/seedance_video_generate.py`, `src/skills/remotion_assemble.py`, `src/services/fast_mode.py`, `src/routers/portfolio.py`, `src/tools/poster_extractor.py`(新), `src/tools/portfolio_hook.py`(保留兜底) |

## 一、Context

`/works` 与 `/library` 视频卡片自 2026 年初上线起反复出现「黑底无缩略图」问题。
2026-05-17 用户第三次反馈该问题，根因如下：

- 唯一的 poster 生产者是 `src/tools/portfolio_hook.py::rebuild_portfolio_listener`，
  通过 `WebhookManager` 订阅 `EVENT_PIPELINE_COMPLETED`
- 该事件**只**在 LangGraph 16-node 完整 pipeline 跑完时触发
- Fast Mode（`/api/fast/generate`）直接调用 `SeedanceClient`，不走 LangGraph，
  不发 `pipeline.completed`
- 直接调用 `seedance_video_generate` skill 或 `remotion_assemble` skill 也不发
- 用户日常使用最多的入口是 Fast Mode，于是大部分视频从未被抽帧

之前的 v0.2.0 / v0.2.2 / v0.2.4 都打过补丁（增加 `_ensure_thumbnails()`、迁移到
`portfolio_hook`、batch 脚本 rsync），但都没解决根因——**生产入口不止一个，钩子只有一个**。

## 二、Decision

抛弃「靠单一全局事件触发」的设计，改成**去中心化的 4 入口 + 1 router backstop**：

- 把 ffmpeg 抽帧逻辑提取到 `src/tools/poster_extractor.py::ensure_poster()`
  作为 SSOT
- 在每个**写 mp4 的代码路径**末尾内联 `ensure_poster(video_path)`，best-effort，
  错误吞掉不影响主流程
- 在 `src/routers/portfolio.py::_thumbnail_path_for` 增加 backstop：响应
  `/api/portfolio/` 时若发现 poster 文件不存在，立刻 ffmpeg 抽一帧再返回。30 秒
  的 `_CACHE_TTL` 摊销 ffmpeg 调用开销
- 保留 `portfolio_hook._ensure_thumbnails()`，与新入口幂等（已存在 + mtime
  ≥ source.mtime 直接 skip），灾备 / 外部脚本写入文件时仍能补抽

## 三、当前实现

入口点（按调用顺序）：

- [src/tools/poster_extractor.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/tools/poster_extractor.py) — `ensure_poster()` SSOT
- [src/skills/seedance_video_generate.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/skills/seedance_video_generate.py) — 真实视频通过 self_verify 后调用
- [src/skills/remotion_assemble.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/skills/remotion_assemble.py) — primary mp4 + 每个 aspect-ratio 变体
- [src/services/fast_mode.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/services/fast_mode.py) — Fast Mode 返回 result 前
- [src/routers/portfolio.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/routers/portfolio.py) — `_thumbnail_path_for` backstop
- [src/tools/portfolio_hook.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/tools/portfolio_hook.py) — `_ensure_thumbnails()` batch 兜底（保留）

命名约定（4 个入口 + backstop 共享）：

```
output/<category>/<stem>.mp4
   ↓
output/thumbnails/portfolio_posters/<category>__<stem>.jpg
```

ffmpeg 参数：`-ss 00:00:02 -vf scale=480:-2 -q:v 3`，seek 失败自动 fallback 到不
带 `-ss` 的重试。失败再失败时返回 `None`，**不 raise**。

## 四、Consequences

**好处**：

- 任何写 mp4 的代码路径都能保证有缩略图，不依赖钩子触发
- 即使新增第 5、第 6 种生产入口，只要在写完文件后调一句 `ensure_poster()` 就完事
- Backstop 让历史已有视频（migration 前的存量）首次被 listing 时也能补抽
- 30s `_CACHE_TTL` + 幂等检查保证 ffmpeg 不会被重复调用

**代价**：

- 4 个生产端各加 5-8 行调用代码（接受）
- ffmpeg 必须在生产容器中安装（已经是 `Dockerfile.backend` 默认依赖）
- 抽帧失败时静默——日志只打 DEBUG，不打 ERROR，避免被无效告警淹没
  （有意为之；缺图会在前端 fallback 到 `<FilmSlate>` 占位，用户可见）
- Backstop 让 `/api/portfolio/` GET 在罕见情况下变成"读取兼写入"，可能在并发
  请求同一缺图视频时重复抽几帧（idempotent，不会损坏文件）

## 五、Alternatives Considered

| 方案 | 拒绝理由 |
|---|---|
| **A. 给 fast_mode 也发 pipeline.completed** | 语义不对——pipeline.completed 是 LangGraph 16-node 完成事件，用它给 fast_mode 用是滥用。新增 `fast_mode.completed` 事件会再次形成"只覆盖部分入口"的弱不变性。 |
| **B. 单独写一个 cron 扫存量缺图** | 解决历史存量但不解决新生产，每次新增入口都得记得加 cron。运维负担。 |
| **C. 让前端在缺图时主动调 `/api/posters/synthesize?path=...`** | 多一个 API 端点 + 前端要懂状态机。Backstop 在 listing 接口里做更省心。 |
| **D. 在 `webhook_manager` 里订阅一个新的 `mp4.written` 通用事件** | 需要重构所有写 mp4 的代码点都发事件，比直接 `ensure_poster()` 多一层 indirection，没换来解耦红利。 |

## 六、Rollback Plan

如果 ffmpeg 在某个新部署环境里出问题（例如 ARM 镜像缺包），可以临时：

1. 在 `ensure_poster()` 入口加一个 `if os.getenv("POSTER_EXTRACTION_DISABLED")`
   早返回
2. 让前端 fallback 到 `<FilmSlate>` 占位（已经是当前行为，无需改前端）
3. 不需要改任何调用方，因为 4 个入口都是 best-effort

完全回滚到 v0.2.5 行为：把 `ensure_poster()` 调用从 4 个生产端移除，把
`_thumbnail_path_for` 的 backstop 分支删掉。预计 5 分钟。

## 七、相关代码

- [src/tools/poster_extractor.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/tools/poster_extractor.py)
- [src/skills/seedance_video_generate.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/skills/seedance_video_generate.py)
- [src/skills/remotion_assemble.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/skills/remotion_assemble.py)
- [src/services/fast_mode.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/services/fast_mode.py)
- [src/routers/portfolio.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/routers/portfolio.py)
- [docs/runbooks/thumbnail-missing.md](file:///Users/pray/project/hermes_evo/AI_vedio/docs/runbooks/thumbnail-missing.md)
- [docs/workflows/portfolio-ops-stable.md](file:///Users/pray/project/hermes_evo/AI_vedio/docs/workflows/portfolio-ops-stable.md)
