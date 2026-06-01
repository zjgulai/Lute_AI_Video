---
name: runbook-thumbnail-missing
description: /works 或 /library 视频卡片显示为黑底无缩略图时的诊断与修复流程。涵盖 poster_extractor 失败、ffmpeg 缺失、bind-mount 权限、video stub 文件等场景。
doc_type: runbook
module: portfolio
status: stable
created: 2026-05-17
updated: 2026-06-01
owner: Sisyphus
source: ai
---

# Runbook — Thumbnail Missing on /works or /library

## 触发场景

- 用户反馈 /works 或 /library?tab=materials 视频卡片大量显示黑色 `<FilmSlate>` 图标
- 监控发现 `/api/portfolio/?kind=final_work` 返回的 `thumbnail_path` 字段大量为 `null`
- `output/thumbnails/portfolio_posters/` 目录下文件数远小于 `output/{renders,seedance,fast_mode}/` 视频文件数

## 影响范围

- 用户体验：视频卡片美观度下降，但可以正常播放（点击进入弹窗使用 `<video>` 元素自身首帧）
- 业务影响：无功能损失，仅视觉退化

## 预期 MTTR

5-15 min（诊断 + 决定走哪条修复路径）

## 相关代码

- [scripts/portfolio_thumbnail_coverage.py](../../scripts/portfolio_thumbnail_coverage.py) — 只读覆盖率 dry-run，不会生成 poster
- [src/tools/poster_extractor.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/tools/poster_extractor.py) — `ensure_poster()` SSOT
- [src/routers/portfolio.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/routers/portfolio.py) — `_thumbnail_path_for` backstop
- [src/skills/seedance_video_generate.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/skills/seedance_video_generate.py) — Seedance 生产入口
- [src/skills/remotion_assemble.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/skills/remotion_assemble.py) — Remotion 生产入口
- [src/services/fast_mode.py](file:///Users/pray/project/hermes_evo/AI_vedio/src/services/fast_mode.py) — Fast Mode 生产入口
- [configs/thumbnail-coverage-dry-run-contract.yaml](../../configs/thumbnail-coverage-dry-run-contract.yaml) — dry-run 覆盖率契约
- [ADR-005](../architecture/adr/005-poster-extraction-everywhere.md) — 设计决策

## 立即诊断

本地或生产修复前先跑 DRY RUN。该命令只读 `output/` 和已有 poster 文件，不会生成 poster、不调用 `ffmpeg`、不触发 provider：

```bash
python scripts/portfolio_thumbnail_coverage.py --output-dir output
python scripts/portfolio_thumbnail_coverage.py --output-dir output --format json
```

生产容器内同样先 dry-run：

```bash
sudo docker exec ai_video_backend python scripts/portfolio_thumbnail_coverage.py --output-dir /app/output
```

```bash
# 1. 远程登陆生产
ssh -i ai_video.pem ubuntu@101.34.52.232

# 2. 通过 API 抓只读覆盖率（portfolio listing 只读取已有 poster，generate_missing=False）
sudo docker exec ai_video_backend python -c "
import json, urllib.request
req = urllib.request.Request('http://localhost:8001/api/portfolio/?kind=final_work&limit=500',
                              headers={'X-API-Key': 'ai_video_demo_2026'})
data = json.loads(urllib.request.urlopen(req).read())
files = data['files']
with_thumb = sum(1 for f in files if f.get('thumbnail_path'))
print(f'TOTAL: {len(files)}  WITH_THUMB: {with_thumb}  MISSING: {len(files) - with_thumb}')
for f in files[:5]:
    print(f\"  {f['path']:50s} thumb={f.get('thumbnail_path')!r}\")
"

# 3. ffmpeg 是否在容器里
sudo docker exec ai_video_backend which ffmpeg && \
  sudo docker exec ai_video_backend ffmpeg -version 2>&1 | head -1

# 4. poster 目录存在 + 可写
sudo docker exec ai_video_backend ls -la /app/output/thumbnails/portfolio_posters/ | head -5
sudo docker exec ai_video_backend touch /app/output/thumbnails/portfolio_posters/.write_test && \
  sudo docker exec ai_video_backend rm /app/output/thumbnails/portfolio_posters/.write_test

# 5. 实地抽一张试试 backstop
sudo docker exec ai_video_backend python -c "
from src.tools.poster_extractor import ensure_poster
from pathlib import Path
videos = list(Path('/app/output/seedance').glob('*.mp4'))
if videos:
    v = videos[0]
    print(f'TEST FILE: {v} size={v.stat().st_size}')
    p = ensure_poster(v)
    print(f'RESULT: {p}  exists={p.is_file() if p else None}')
"
```

## 分类响应

### 场景 A：ffmpeg 缺失

诊断信号：步骤 3 输出 `ffmpeg: command not found`，或者 `ensure_poster` 返回 `None`
且 backend 日志出现 `poster_extractor: ffmpeg not found`。

**根因**：`Dockerfile.backend` 改动导致 ffmpeg 被剔除（极少见，会影响 seedance
duration verify、whisper 等多个功能，应该被冒烟测试拦下）。

**修复**：

```bash
# 1. 临时：在容器里手装
sudo docker exec -u root ai_video_backend apt-get update && \
  sudo docker exec -u root ai_video_backend apt-get install -y --no-install-recommends ffmpeg

# 2. 长期：检查 Dockerfile.backend 第 24-25 行
grep -A1 "apt-get install" Dockerfile.backend | head -5
# 应当包含 ffmpeg。如缺失，恢复后 rebuild：
sudo docker compose -f deploy/lighthouse/docker-compose.prod.yml build backend
sudo docker compose -f deploy/lighthouse/docker-compose.prod.yml up -d --force-recreate backend
```

### 场景 B：poster 目录权限错误

诊断信号：步骤 4 `touch` 失败，提示 Permission denied。

**根因**：容器 `appuser`(uid 1000) 对 `/app/output/thumbnails/portfolio_posters/`
没有写权限。`backend_output` volume 是 Docker named volume，第一次创建时由
root 所有，appuser 不能写入。

**修复**：

```bash
sudo docker exec -u root ai_video_backend chown -R appuser:appgroup \
  /app/output/thumbnails/
```

### 场景 C：视频文件是 stub（< 1 MiB）

诊断信号：缺图的视频 `size_bytes` < 1048576。

**根因**：seedance fallback / 内容审核失败时写的占位 mp4。**这些视频本来就不会
出现在 `/api/portfolio/?kind=final_work`** 里（router `_scan_portfolio` 在
[src/routers/portfolio.py:202](file:///Users/pray/project/hermes_evo/AI_vedio/src/routers/portfolio.py#L202)
过滤掉 ≤ 1 MiB 的非音频文件）。

**修复**：无需修复。如果用户看到的恰好是 stub 视频，引导他们重跑生成。

### 场景 D：4 个生产端有一个新增了，没接 ensure_poster

诊断信号：缺图视频集中在某一类目（例如全部是 `output/new_skill/`），说明该路径
是新加的生产入口但忘了内联调用。

**根因**：新加的 skill 没读 ADR-005。

**修复**：在该 skill 写完 `.mp4` 后加：

```python
try:
    from src.tools.poster_extractor import ensure_poster
    ensure_poster(video_path)
except Exception:
    pass
```

`portfolio.py::_thumbnail_path_for(..., generate_missing=True)` 仍可被后台 hook 或脚本显式使用，但 request handler 当前保持 `generate_missing=False`，所以 listing 本身不生成 poster。

### 场景 E：批量历史视频缺图

诊断信号：步骤 2 显示 MISSING 很多，但都是几天/几周前的视频；新生成的有图。

**根因**：v0.2.6 之前生产环境的视频，从未触发过任何 poster 入口。

**修复（推荐）**：先 dry-run 确认缺口，再显式运行批量生成脚本：

```bash
sudo docker exec ai_video_backend python scripts/portfolio_thumbnail_coverage.py --output-dir /app/output
sudo docker exec ai_video_backend python scripts/generate_portfolio_thumbnails.py
sudo docker exec ai_video_backend python scripts/portfolio_thumbnail_coverage.py --output-dir /app/output
```

不要依赖 `/api/portfolio/` listing 自动补图。当前 request path 是只读的 `generate_missing=False`，这是为了避免列表接口在用户请求中触发 `ffmpeg`。

**修复（局部）**：只针对单个视频测试 `ensure_poster()`：

```bash
sudo docker exec ai_video_backend python -c "
from src.tools.poster_extractor import ensure_poster
ensure_poster('/app/output/renders/example.mp4')
"
```

## 永久 fix（已落地）

- ADR-005（2026-05-17）将 poster 生成从「单一 LangGraph 钩子」改为「4 入口 + opt-in backstop」。详见 [ADR-005](../architecture/adr/005-poster-extraction-everywhere.md)。
- 覆盖率统计走 `scripts/portfolio_thumbnail_coverage.py`；它是 DRY RUN，只读扫描，不生成文件。
- 任何新增的 video-producing skill，**必须**在写完 `.mp4` 后调用
  `ensure_poster()`。这条规则会在 PR review 检查表里。

## 相关文档

- [ADR-005 — Poster Extraction at Every Video Producer](../architecture/adr/005-poster-extraction-everywhere.md)
- [Portfolio 运营文档](../workflows/portfolio-ops-stable.md)
- [Runbook 索引](./README.md)
