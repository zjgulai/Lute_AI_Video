# Phase 3 Runbook -- End-to-End Real Video Pipeline

## Prerequisites

- Python 3.12 virtualenv active
- Docker running (for PostgreSQL)
- Node.js 22+ available
- `.env` with valid API keys

## Known API Status (审计结果)

| API | 状态 | 说明 |
|-----|------|------|
| Kimi (LLM) | ✅ 就绪 | OPENAI_API_KEY 已设置，超时 120s |
| Seedance (poyo.ai) | ⚠️ 待测 | POYO_API_KEY 已设置，历史上有 403/HTTP2 兼容问题 |
| ElevenLabs TTS | ❌ 缺失 | ELEVENLABS_API_KEY 未设置，将使用 poyo/Suno（音乐非语音） |
| GPT-Image | ✅ 就绪 | OPENAI_API_KEY 已设置，将直连 OpenAI |
| Remotion | ❌ 绑定错误 | macOS 原生绑定在 Linux 上不兼容 |
| PostgreSQL | ⚠️ 待测 | DATABASE_URL 已设置，需 Docker 运行 |
| ffmpeg | ✅ 可用 | 用于 stub 回退视频生成 |

## Step 1: Fix Remotion Bindings

**问题诊断：** `node_modules` 在 macOS 上安装，包含 `darwin-arm64` 原生绑定（`@remotion/compositor-darwin-arm64`、`@rspack/binding-darwin-arm64`）。在当前 Linux aarch64 容器中缺少 `linux-arm64-gnu` 版本的原生绑定，导致 `npx remotion --version` 崩溃。

**修复（在运行后端的主机上执行）：**

```bash
cd ~/project/hermes_evo/AI_vedio/rendering/

# 删除旧的 macOS 原生绑定，重新安装当前平台的版本
rm -rf node_modules package-lock.json
npm install

# 验证 Remotion 可用
npx remotion --version
# 预期：输出版本号，如 "v4.x.x"

# 如果仍然报错 "Cannot find native binding"：
# 1. 确认当前平台：
uname -m   # arm64 或 x86_64
# 2. 手动安装对应平台的 binding：
#    arm64 Linux: npm install @rspack/binding-linux-arm64-gnu @remotion/compositor-linux-arm64-gnu
#    x64 Linux:   npm install @rspack/binding-linux-x64-gnu @remotion/compositor-linux-x64-gnu
#    macOS:       npm install（自动选择 darwin-arm64/darwin-x64）

cd ..
```

**注：** 如果 Remotion 修复后仍然不可用，assemble_final 步骤将使用 ffmpeg stub 回退，生成 5 秒纯色视频。这不阻塞其他步骤。

## Step 2: Start Services

```bash
# Terminal 1: PostgreSQL
docker start ai_video_postgres  # or docker-compose up -d

# Terminal 2: Backend
cd ~/project/hermes_evo/AI_vedio
source .venv/bin/activate
python scripts/diagnose_apis.py  # check all APIs first
uvicorn src.api:app --reload --port 8001

# Terminal 3: Frontend
cd web/
npm run dev
```

## Step 3: Run Pipeline

1. Open http://localhost:3000
2. Select "shang pin zhi pai" scenario
3. Product: "yunfu zhen", Brand: "Momcozy"
4. Click "pei zhi wan cheng -->"
5. Execute steps one by one
6. Record results in `docs/spike/2026-04-28_s1-real-failures.md`

## Step 4: Verify Persistence

1. Stop backend (Ctrl+C in Terminal 2)
2. Restart: `uvicorn src.api:app --reload --port 8001`
3. Refresh browser, verify pipeline state is preserved
4. Continue executing remaining steps

## Fallback Plan

- If Seedance fails: Note the error, continue with stub clips
- If TTS fails: Note the error, continue with stub audio
- If Remotion fails: Skip assemble, note as blocker
- If all media fails: Document all errors, plan API key procurement for tomorrow

## Troubleshooting

### PostgreSQL not starting

```bash
docker logs ai_video_postgres
docker restart ai_video_postgres
# If container doesn't exist:
docker run --name ai_video_postgres -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=ai_video -p 5432:5432 -d postgres:16
```

### Virtualenv not found

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Node.js version mismatch

```bash
node --version  # should be 22+
# If not: install via nvm
nvm install 22
nvm use 22
```

### API keys not loading

```bash
# Verify .env exists at project root
ls -la .env
# Verify diagnose script sees them
python scripts/diagnose_apis.py
```
