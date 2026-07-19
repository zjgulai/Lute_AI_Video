---
title: Portfolio 与 Asset Library 运营文档
doc_type: workflow
module: portfolio
status: stable
created: 2026-05-08
updated: 2026-07-11
owner: self
source: human+ai
---

## Portfolio / Asset Library

闭环测试通过真实外部 API 跑出的 mp4 / mp3 / png / wav / keyframe 都是付费产物,作为
作品集 + 数据资产保留。

### `/api/portfolio/` 端点 (`src/routers/portfolio.py`)

- **扫描范围**: `OUTPUT_DIR` 下 13 个固定子目录,`rglob` 全量递归扫描
- **过滤**: 扩展名白名单 + 视频/图片 > 1 MiB(过滤 stub) + 音频任意正大小
- **缓存**: 30s 进程内存缓存(`_CACHE`),单 key `"all"`
- **排序**: `?sort=quality` — renders(0) > fast_mode(1) > 其他(99),同类按 `produced_at` desc
  其他选项:`recent`(默认)/`size_desc`/`size_asc`
- **分页**: `?limit=N&offset=M`,`total` 字段返回过滤后总数,`by_category` 始终聚合全集
- **Poster**: `thumbnail_path` 字段指向 jpg(`output/thumbnails/portfolio_posters/`),
  由 `_thumbnail_path_for` 解析。如果文件缺失,**router 内联通过 ffmpeg 现抽一帧**
  (见下方"Thumbnail 生成"),保证 /works 与 /library 视频卡片永远有缩略图

### Media 访问的 Canonical backend proxy (`deploy/lighthouse/ai_video_locations.conf`)

`/api/media/` 的 active stable 契约是全部反向代理到 backend；protected runtime media
必须经过 FastAPI 的 tenant-bound 签名校验，Nginx 不能直接读取整个
`backend_output` 文件系统。Active 配置为：

```nginx
# Canonical backend proxy; authorization and cache policy stay in FastAPI.
location /api/media/ {
    proxy_pass http://ai_video_backend;
    include /etc/nginx/proxy_params.conf;
}
```

客户端访问 protected media 时，执行路径只有下列一条：

1. 携带已认证的 API 上下文请求
   `GET /api/media/sign?path=<url-encoded-canonical-path>&purpose=view`。
2. 使用响应中的短期签名 URL 请求精确 media path；不要自报 tenant，不要将
   签名 URL 持久化到业务 state 或 database。
3. 只有 `brand_assets` 与 `demo` 两个显式 public root 可按 backend policy 匿名读取；
   其他 unsigned runtime path 必须 fail closed。

#### Historical / non-canonical（禁止恢复）

早期方案曾由 Nginx 对运行时输出目录做 direct filesystem alias，并以
local-file-first 方式 fallback backend。该方案会绕过 backend 的租户鉴权和签名约束，
仅作历史背景，不是可执行运维步骤。早期的 Nginx 直送性能数据也不再代表当前路径。

- `/api/assets/` 与 `/api/portfolio/` 同为 listing 端点,nginx burst 均设为 100,
  避免连续切换 Library tab 时触发 429(`api_video_locations.conf` 自 v0.2.6 起对齐)

### Thumbnail 生成 (ADR-005 / `src/tools/poster_extractor.py`)

v0.2.6 起 thumbnail 生成走"4 入口 + 1 backstop"的去中心化模型,**不再依赖 LangGraph
`pipeline.completed` 单一钩子**(后者仅覆盖完整 16-node pipeline,fast_mode 等旁路场景从前
全部漏抽,/works 显示黑底)。

**ffmpeg 参数(统一在 `ensure_poster()`)**: `-ss 00:00:02 -vf scale=480:-2 -q:v 3`,
若 seek 失败(短视频 < 2s)自动 fallback 到不带 `-ss` 的重试一次。

**4 个生产端入口(写完 mp4 后内联调用,best-effort 吞掉错误)**:

- `src/skills/seedance_video_generate.py` — Seedance 真实视频生成
- `src/skills/remotion_assemble.py` — Remotion 最终合成 + 多 aspect ratio fan-out
- `src/services/fast_mode.py` — Fast Mode 直接文字→视频
- `src/tools/portfolio_hook.py` `_ensure_thumbnails()` — 完整 pipeline 完成后 batch
  扫描兜底(历史遗留,仍保留,与新入口幂等)

**1 个 router backstop**:

- `src/routers/portfolio.py::_thumbnail_path_for` 在响应 `/api/portfolio/` 时若发现
  poster 缺失,立刻调用 `ensure_poster()` 抽一帧再返回。30s 缓存摊销开销

**命名约定**: `output/<category>/<filename>.mp4` →
`output/thumbnails/portfolio_posters/<category>__<filename_stem>.jpg`,
分隔符 `__` 由 `Path.relative_to(OUTPUT_DIR)` 的 `/` 替换得到

**幂等性**: 已存在且 `poster.mtime >= video.mtime` 直接返回路径,不重抽

### Footage 页面 (`web/src/app/footage/page.tsx` 已迁移到 `/works` + `/library`)

- **/works**: `final_work` 类目(renders + fast_mode 视频),`<img src={thumbUrl}>` +
  `<FilmSlate>` 缺图占位。预览弹窗使用 `<video poster={thumb}>`
- **/library?tab=materials**: `creation_intermediate` 类目(seedance / gpt_images /
  audio / keyframes / character_identity / uploads),四类过滤(全部/视频/图片/音频)
- **/library?tab=brand_kit**: `brand_kit` 类目(brand_assets 子目录),按 product 分组
- **/library?tab=influencers**: 走 `/api/assets/influencers` 端点(legacy `api_assets.py`)

### 索引与 sync(遗留)

**索引** (`assets/portfolio/index.json`,gitignored):

- `scripts/portfolio_index.py` 扫 12 子目录输出 JSON(供离线/CI 使用)
- `/api/portfolio/` 端点**不读此 JSON**,运行时直接扫文件系统

**双向 sync 脚本**:

- `scripts/sync_output_to_lighthouse.sh`:本地 output/ → 生产 volume
- `scripts/sync_lighthouse_to_output.sh`:生产 volume → 本地 output/

**遗留批量脚本** `scripts/generate_portfolio_thumbnails.py`:
v0.2.6 之前用于本地预生成 + rsync 到生产。新架构后**只在初始化或灾备场景使用**,日常
开发不需要手动跑(每次 video 生成自带 poster + router backstop 兜底)。

---

## 相关文档

- [ADR-005 — Poster Extraction at Every Video Producer](../architecture/adr/005-poster-extraction-everywhere.md)
- [Runbook — Thumbnail Missing](../runbooks/thumbnail-missing.md)

