# AI Video Pipeline — Leadership Demo Run-Book

**Date:** 2026-05-04 ~ 2026-05-08  
**Presenter:** You  
**Audience:** Leadership / stakeholders  
**Goal:** Demonstrate end-to-end AI video generation for baby-feeding vertical (Path A)

---

## 1. Prerequisites (check before demo)

| # | Check | Command / Location |
|---|-------|--------------------|
| 1 | Mac terminal ready | `cd ~/project/hermes_evo/AI_vedio` |
| 2 | Python venv active | `source .venv/bin/activate` |
| 3 | Backend starts cleanly | `python -m src.api` → http://localhost:8001 |
| 4 | Frontend dev server running | `cd web && npm run dev` → http://localhost:5173 |
| 5 | Node v22 available | `node -v` (should print v22.x) |
| 6 | ffmpeg available | `ffprobe -version` (optional but recommended) |
| 7 | **API keys** (see §6) | `.env` or environment exported |

---

## 2. Demo Agenda (~6 minutes)

| Time | Section | What to Say |
|------|---------|-------------|
| 0:00 | Hook | "过去做一条产品视频需要编剧+拍摄+剪辑+配音，周期3天。今天AI全流程5分钟出片。" |
| 0:30 | **S1 商品直拍** | 输入商品信息 → 策略 → 脚本 → 分镜 → AI生成视频+配音+缩略图 → 审计 |
| 2:30 | **S2 品牌宣传** | 同一套pipeline，打开brand_mode，自动加入品牌合规审查 |
| 3:30 | **S3 网红二创** | 粘贴网红视频链接 → AI分析 → 二创脚本 → 重新合成成片 |
| 4:30 | **Media 播放器** | 点开"媒体"Tab，展示 `<video>` 播放最终成片，播放TTS配音 |
| 5:00 | **Audit 审计** | 展示7维度质量报告：产品露出、语言一致性、时长、品牌对齐… |
| 5:30 | Close | "所有环节都是Skill驱动，不是prompt拼贴；关键产出点带自证+审计，确保上线质量。" |

---

## 3. Scenario Walkthrough

### 3.1 S1 — 商品直拍 (Product Direct)

**Frontend path:** 首页 → 选择「商品直拍」 → 填写表单

**Backend call (curl 备用):**
```bash
curl -s http://localhost:8001/scenario/s1 \
  -H "Content-Type: application/json" \
  -d '{
    "product_catalog": {
      "name": "Wearable Breast Pump X1",
      "category": "baby_feeding",
      "usps": ["hands-free", "hospital-grade suction", "quiet <40dB"]
    },
    "target_platforms": ["tiktok", "shopify"],
    "target_languages": ["en"],
    "week": "2026-W18"
  }' | jq .
```

**What to expect:**
- 11 steps complete
- `clip_paths`, `audio_paths`, `thumbnail_image_paths` populated
- `final_video_path` → playable .mp4
- `audit_report` with 7 criteria

---

### 3.2 S2 — 品牌宣传 (Brand Campaign)

**Frontend path:** 首页 → 选择「品牌宣传片」 → 填写品牌表单

**Backend call (curl 备用):**
```bash
curl -s http://localhost:8001/scenario/s2 \
  -H "Content-Type: application/json" \
  -d '{
    "brand_package": {
      "brand_name": "DemoBrand",
      "tone": "warm, professional",
      "colors": ["#FFC0CB", "#FFFFFF"]
    },
    "target_platforms": ["tiktok", "shopify"],
    "target_languages": ["en"]
  }' | jq .
```

**Key difference from S1:** `brand_mode=True` triggers Step 3 **brand-compliance audit**.

---

### 3.3 S3 — 网红二创 (Influencer Remix)

**Frontend path:** 首页 → 选择「网红二创带链接」 → 粘贴视频URL

**Backend call (curl 备用):**
```bash
curl -s http://localhost:8001/scenario/s3 \
  -H "Content-Type: application/json" \
  -d '{
    "video_url": "https://tiktok.com/@jessica/video/demo",
    "product": {
      "name": "Wearable Breast Pump X1",
      "brand_name": "DemoBrand",
      "usps": ["hands-free", "hospital-grade suction", "quiet <40dB"]
    },
    "influencer_name": "Jessica",
    "brief_id": "demo_s3"
  }' | jq .
```

---

## 4. Media Playback

Files are served via:
```
GET http://localhost:8001/api/media/{filename}
```

The frontend **Media** Tab automatically:
- Plays `final_video_path` in `<video controls>`
- Renders `thumbnail_image_paths` in `<img>` grid
- Lists `audio_paths` with `<audio controls>`
- Shows `clip_paths` preview grid

If you need a quick browser sanity check:
```bash
open "http://localhost:8001/api/media/$(ls output/renders/*.mp4 | head -1 | xargs basename)"
```

---

## 5. Quality Audit

Every full pipeline run ends with an `audit_report`:

```json
{
  "overall_status": "PASS|WARN|FAIL",
  "overall_score": 0.87,
  "summary": "...",
  "criteria": [
    {"name": "product_mention", "status": "PASS", "score": 1.0, ...},
    ...
  ]
}
```

**Leadership talking points:**
- "技术自证": 每个媒体Skill在输出时自动检查文件头、大小、时长。
- "语义审计": 跨产物检查产品名是否出现、语言是否一致、缩略图是否对齐品牌色。
- "不是黑盒": 审计结果是结构化JSON，可接入CI/CD拦截低质量内容上线。

---

## 6. API Keys & Cost

| Service | Key Name | Purpose | Approx Cost |
|---------|----------|---------|-------------|
| OpenAI | `OPENAI_API_KEY` | GPT-4o / GPT-Image-1 图像生成 + 脚本/策略 | ~$5-10 |
| ElevenLabs | `ELEVENLABS_API_KEY` | TTS 配音生成 | Free tier (10k chars/mo) |
| Seedance | `SEEDANCE_API_KEY` | 视频片段生成 (text-to-video) | ~$3-5 |

**Procurement checklist:**
- [ ] OpenAI key with "gpt-image-1" access (需要Tier 1+)
- [ ] ElevenLabs key (免费注册)
- [ ] Seedance key (种子轮平台，官网申请)

**Environment setup:**
```bash
export OPENAI_API_KEY="sk-..."
export ELEVENLABS_API_KEY="..."
export SEEDANCE_API_KEY="..."
```

Or write to `.env` in project root (已支持 `python-dotenv`).

---

## 7. Fallback Plans

### Plan A — Real Mode (有API Key)
直接运行上述Scenario，生成真实.mp4/.mp3/.png，领导当场看到AI视频。

### Plan B — Stub Mode (无API Key)
代码本身支持 **零Key运行**。所有媒体Skill会输出合法占位文件（带正确magic header），pipeline完整跑通，审计也会给出结构化报告。

**Stub模式启动：**
```bash
# 不设置任何API key，直接运行
python scripts/test_media_skills_e2e.py        # 22/22 PASS
python scripts/test_s1_unified_e2e.py          # 全链路 PASS
```

**Stub模式Demo话术：**
> "今天是代码走查环境，API key还没到位，但整个pipeline已经贯通。这是自动生成的占位文件（带MP4/MP3/PNG合法文件头），一旦key到位立刻出真实视频。这里是审计报告，证明我们的质检体系已经建好。"

### Plan C — 预缓存视频
如果担心现场网络波动，可提前跑好一次，把产物复制到 `output/demo/`：
```bash
cp output/renders/*.mp4 output/demo/
cp output/gpt_images/*.png output/demo/
```
然后直接播放本地文件。

---

## 8. Troubleshooting

| Symptom | Fix |
|---------|-----|
| `ModuleNotFoundError: No module named 'src'` | 确保在项目根目录运行；`pwd` 应包含 `AI_vedio` |
| `Skill 'seedance-video-generate-skill' not found` | 先执行 `import src.skills.seedance_video_generate` 触发auto-register |
| 前端 Media Tab 视频黑屏 | 检查后端 `/api/media/{filename}` 是否返回200；浏览器DevTools → Network |
| `audit overall_status=FAIL` on stubs | **正常**。审计诚实地报告了占位文件尺寸不足；换成真实API后自动PASS |
| npm install 报错 | 使用 `npm install --legacy-peer-deps` 或确认Node v22 |

---

## 9. Quick Smoke Test (Demo前必跑)

```bash
# Terminal 1 — 后端
source .venv/bin/activate
python -m src.api

# Terminal 2 — 前端
cd web && npm run dev

# Terminal 3 — 冒烟
python scripts/test_media_skills_e2e.py
python scripts/test_s1_unified_e2e.py
```

期望结果：
- `test_media_skills_e2e.py` → **22/22 PASS**
- `test_s1_unified_e2e.py` → **全绿**

---

## 10. File Map (Demo时可随手引用)

```
src/pipeline/s1_product_pipeline.py   ← 统一S1∪S2 (11步)
src/pipeline/s2_brand_pipeline.py     ← 兼容包装器 (delegate to S1)
src/pipeline/s3_remix_pipeline.py     ← 网红二创 (9步)
src/api.py                             ← FastAPI + /api/media/{filename}
web/src/components/OneShotResultView.tsx ← Media Tab + Video Player
scripts/test_media_skills_e2e.py       ← 5个新Skill冒烟
scripts/test_s1_unified_e2e.py         ← S1∪S2全链路冒烟
```

---

**祝交付顺利 🎯**
