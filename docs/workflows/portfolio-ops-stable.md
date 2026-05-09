---
title: Portfolio 与 Asset Library 运营文档
doc_type: workflow
module: portfolio
status: stable
created: 2026-05-08
updated: 2026-05-08
owner: self
source: human+ai
---

## Portfolio / Asset Library

闭环测试通过真实外部 API 跑出的 mp4 / mp3 / png / wav / keyframe 都是付费产物,作为
作品集 + 数据资产保留。

### `/api/portfolio/` 端点 (`src/routers/portfolio.py`)

- **扫描范围**: `OUTPUT_DIR` 下 12 个固定子目录,`rglob` 全量递归扫描
- **过滤**: 扩展名白名单 + 视频/图片 > 1 MiB(过滤 stub) + 音频任意正大小
- **缓存**: 30s 进程内存缓存(`_CACHE`),单 key `"all"`
- **排序**: `?sort=quality` — renders(0) > fast_mode(1) > 其他(99),同类按 `produced_at` desc
- **截断**: `?limit=50` — 前端 footage 页面只展示 TOP50,`by_category` 仍聚合全量
- **Poster**: `thumbnail_path` 字段指向预生成 jpg(`output/thumbnails/portfolio_posters/`)

### nginx 静态直送 (`deploy/lighthouse/nginx.conf:54-70`)

`/api/media/` 走 `try_files` 先读本地文件,未命中再 fallback backend:

```nginx
location /api/media/ {
    alias /var/www/media/;
    add_header Cache-Control "public, max-age=86400";
    try_files $uri @backend_media;
}
```

- `backend_output` volume 以 `:ro` 挂载到 nginx 容器 `/var/www/media/`
- 生产实测: thumbnail 2.6KB → 4.8ms, video 12.6MB → 32ms(均走 nginx,不穿透 FastAPI)

### Thumbnail 生成 (`scripts/generate_portfolio_thumbnails.py`)

- ffmpeg 抽帧: `-ss 00:00:02 -vf scale=480:-2 -q:v 3`
- 输出: `output/thumbnails/portfolio_posters/<category>__<filename_stem>.jpg`
- 增量: 已存在且 mtime >= source mtime 则跳过
- 本地生成后 `rsync` → 生产 `output_uploaded/` → `docker cp` 进 `lighthouse_backend_output`

### Footage 页面 (`web/src/app/footage/page.tsx`)

- **成品(finished)**: `GalleryGrid` 展示 renders 类目视频,点击弹出 `MediaPreviewModal`
- **素材(materials)**: grid 展示 50 个 item,支持 全部/视频/图片/音频 分类过滤
- **预览**: 统一弹窗 overlay — 视频 autoPlay + controls,图片居中,音频 controls + 文件名
- 不再 `window.open(..., "_blank")`,不再有右侧 detail panel

### 索引与 sync(遗留)

**索引** (`assets/portfolio/index.json`,gitignored):

- `scripts/portfolio_index.py` 扫 12 子目录输出 JSON(供离线/CI 使用)
- `/api/portfolio/` 端点**不读此 JSON**,运行时直接扫文件系统

**双向 sync 脚本**:

- `scripts/sync_output_to_lighthouse.sh`:本地 output/ → 生产 volume
- `scripts/sync_lighthouse_to_output.sh`:生产 volume → 本地 output/

---

