# AI Video Pipeline — Local Development Guide

## Overview

16-node LangGraph pipeline that produces short-form marketing videos with self-audit + human-in-the-loop review.

Pipeline flow:
Strategy → Audit → Script → Audit → Compliance → Storyboard → Asset Sourcing → Media Generation → Edit → Audit → Audio → Caption → Thumbnail → Audit → Distribution → Analytics

4 human review checkpoints (strategy, script, edit, thumbnail) with AI self-audit driving auto-approve/reject decisions.

---

## Prerequisites

- **Python 3.11+** with pip
- **Node.js 18+** with npm (for WebUI + Remotion rendering)

Check:
```
python3 --version && node --version && npm --version
```

---

## Quick Start（本地开发）

### 1. Python 后端

```bash
cd /Users/pray/project/hermes_evo/AI_vedio

# 创建虚拟环境（仅首次，如已存在则跳过）
python3 -m venv .venv

# 激活虚拟环境（每次新开终端都要执行！）
source .venv/bin/activate

# 安装后端依赖（仅首次）
pip install -r requirements.txt

# 启动 FastAPI 服务器
python3 -m uvicorn src.api:app --reload --port 8001
```

后端地址 `http://localhost:8001`，可以用 `http://localhost:8001/health` 验证。

### 2. WebUI（Next.js）

新开一个终端窗口：

```bash
cd /Users/pray/project/hermes_evo/AI_vedio

# 激活虚拟环境
source .venv/bin/activate

# 进入前端目录
cd web

# 安装前端依赖（仅首次）
npm install

# 启动开发服务器
npm run dev
```

WebUI runs at `http://localhost:3000`

### 3. Use the WebUI

1. Open http://localhost:3000
2. (Optional) Click "Configure API Keys" to enter your API keys directly
3. Click "Start Pipeline"
4. The pipeline runs to first review checkpoint
5. Review AI self-audit report, approve/reject/request changes
6. Repeat for all 4 checkpoints
7. Final output: scripts, storyboards, caption plans, thumbnail variants, distribution plans

### 4. Generate .mp4 (Remotion)

After pipeline completes, the state JSON is at `output/renders/<run>_state.json`.

```bash
cd AI_vedio/rendering
npm install        # one-time
npx tsx src/render.ts --input ../output/renders/demo_output_state.json --output ../output/video.mp4
```

---

## API Key Configuration

### Option A: WebUI (recommended for first use)
At http://localhost:3000, click "Configure API Keys" and enter keys. They're sent with the pipeline request and injected into the server's environment. Works immediately, no restart needed.

### Option B: .env file
```bash
cp .env.example .env
# Edit .env with your keys
ANTHROPIC_API_KEY=sk-...
OPENAI_API_KEY=sk-...
ELEVENLABS_API_KEY=...
```

### Option C: Direct API call
```bash
curl -X POST http://localhost:8001/pipeline/start \
  -H "Content-Type: application/json" \
  -d '{
    "api_keys": {
      "ANTHROPIC_API_KEY": "sk-...",
      "OPENAI_API_KEY": "sk-..."
    },
    "target_platforms": ["tiktok", "facebook"],
    "target_languages": ["en"]
  }'
```

If no keys are provided anywhere, the pipeline runs in **mock mode** — produces natural-language placeholder content without calling any external API.

---

## Architecture

```
web/                    Next.js 16 — Review UI (TypeScript + Tailwind CSS 4)
rendering/              Remotion 4 — .mp4 video renderer (TypeScript, standalone)
src/
  api.py                FastAPI backend — pipeline endpoints, review submission
  config.py             Configuration — reads from os.environ (not .env directly)
  graph/
    pipeline.py         LangGraph pipeline compilation + checkpoint config
    nodes.py            16 node functions (strategy → analytics)
    routing.py          Conditional routing with retry guard + audit guard
  agents/
    strategy_writer.py  Content calendar generation
    script_writer.py    Multi-language script writer (EN/ES/FR/DE)
    auditor.py          Self-audit scoring (4 checkpoints)
    compliance.py       Brand compliance pre-check
    storyboard.py       Visual shot planning
    asset_sourcing.py   Asset library search (Supabase/pgvector or mock)
    caption.py          Caption plan generation
    thumbnail.py        Thumbnail variant generation
    media_generation.py DALL-E image generation (or mock)
    editor.py           Video editing composition plan
    audio_designer.py   Audio plan + TTS (ElevenLabs or mock)
    distribution.py     Platform distribution plan
    analytics.py        Performance analytics report
    i18n.py             Internationalization service
  tools/
    llm_client.py       Multi-provider LLM (OpenAI/Anthropic) with timeout + retry
    dalle_client.py     DALL-E 3 with asyncio.timeout(120s) + retry
    elevenlabs_client.py TTS with asyncio.timeout(60s) + retry
    remotion_renderer.py Remotion environment validation
    retry.py            Exponential backoff (3 attempts)
    webhook_manager.py  Event dispatch (audit.completed, pipeline.completed)
    metrics_repository.py Pipeline run persistence (JSON/SQLite)
    error_classifier.py structured error classification
    asset_library.py    Supabase + pgvector asset search
  models/
    state.py            VideoPipelineState (26+ fields)
    __init__.py         Pydantic models + ErrorCode + PipelineError
  telemetry.py          @timed_node decorator + PipelineMetrics
tests/                  381 tests across 22+ files (0 failures)
```

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check + Remotion env report |
| POST | `/pipeline/start` | Start pipeline (accepts optional `api_keys`) |
| GET | `/pipeline/{id}/state` | Get current pipeline state |
| POST | `/pipeline/{id}/review/{node}` | Submit human review (approve/reject/request_changes) |
| GET | `/pipeline/{id}/output` | Get final pipeline output |

---

## Running Tests

```bash
cd AI_vedio
python3 -m pytest tests/ -v --tb=short
```

381 tests, 0 expected failures (7 API tests skip if fastapi not installed).

---

## Project Status

- All 20 hardening gaps (GAP-1 through GAP-20) closed
- Production readiness audit complete
- Mock pipeline run produces full 26-field state with 15/16 nodes executed
- Ready for real LLM content: fill API keys, run with `--live` flag
- Ready for .mp4 rendering: transfer state JSON to Node.js environment with Remotion
