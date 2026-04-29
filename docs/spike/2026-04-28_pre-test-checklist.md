# Pre-Test Checklist -- 2026-04-29 Testing Session

> **Date:** 2026-04-29
> **System:** AI Multi-Scenario Video Creation Platform
> **Scope:** Phase 3 E2E + new components (S1 step-by-step, auto mode, video duration slider, quality dashboard, i18n EN/ZH toggle)
> **Target:** S1 (product direct) + S3 (influencer remix) + persistence verification + i18n

---

## 1. Pre-flight Checks (before starting services)

### 1.1 Environment file
```bash
cd /Users/pray/project/hermes_evo/AI_vedio
test -f .env && echo "EXISTS" || echo "MISSING"
# Expected: EXISTS
# Verify these keys are set:
grep -E "^OPENAI_API_KEY|^POYO_API_KEY|^API_KEY|^DATABASE_URL" .env | head -5
# Expected: OPENAI_API_KEY=sk-...  POYO_API_KEY=sk-...  API_KEY=ai_video_demo_2026
# Note: ELEVENLABS_API_KEY may be empty — silent MP3 fallback is OK
```

### 1.2 Docker (PostgreSQL)
```bash
docker ps --filter name=ai_video_pg --format "{{.Names}} {{.Status}}"
# Expected: ai_video_pg  Up X minutes (healthy)

# If not running:
docker compose -f /Users/pray/project/hermes_evo/AI_vedio/docker-compose.yml up -d postgres

# Verify PG health:
docker exec ai_video_pg pg_isready -U ai_video
# Expected: /var/run/postgresql:5432 - accepting connections
```

### 1.3 Node.js
```bash
node --version
# Expected: v22.x.x (if lower: nvm install 22 && nvm use 22)
```

### 1.4 Python virtual environment
```bash
source /Users/pray/project/hermes_evo/AI_vedio/.venv/bin/activate
python --version
# Expected: Python 3.12.x

# Verify dependencies:
pip list 2>/dev/null | grep -iE "fastapi|uvicorn|pydantic|structlog"
# Expected: at least fastapi, uvicorn, pydantic present
```

### 1.5 Remotion bindings
```bash
cd /Users/pray/project/hermes_evo/AI_vedio/rendering
ls node_modules/.package-lock.json 2>/dev/null && echo "INSTALLED" || echo "NEEDS INSTALL"
npx remotion --version 2>/dev/null || echo "REMOTION FAILS (ffmpeg stub fallback expected)"
# NOTE: Remotion may fail on non-macOS platforms. ffmpeg stub fallback is pre-approved.
```

### 1.6 Output directories
```bash
mkdir -p /Users/pray/project/hermes_evo/AI_vedio/output/{seedance,audio,gpt_images,renders,demo,uploads}
```

---

## 2. Service Startup

### 2.1 Start PostgreSQL (if not already running)
```bash
cd /Users/pray/project/hermes_evo/AI_vedio
docker compose up -d postgres
# Wait for healthy:
sleep 5 && docker exec ai_video_pg pg_isready -U ai_video
```

### 2.2 Run API diagnostics
```bash
cd /Users/pray/project/hermes_evo/AI_vedio
source .venv/bin/activate
python scripts/diagnose_apis.py
# Expected: prints status for each API (Kimi/OpenAI, Seedance/Poyo, etc.)
```

### 2.3 Start backend (Terminal 1)
```bash
cd /Users/pray/project/hermes_evo/AI_vedio
source .venv/bin/activate
uvicorn src.api:app --reload --port 8001 --log-level info
# Expected: "Uvicorn running on http://0.0.0.0:8001"
# NOTE: Port 8001 matches frontend config (API_BASE = localhost:8001)
```

### 2.4 Start frontend (Terminal 2)
```bash
cd /Users/pray/project/hermes_evo/AI_vedio/web
npm run dev
# Expected: "▲ Next.js 14.x"  "Local: http://localhost:3000"
```

---

## 3. Smoke Tests (5 min)

### 3.1 Health endpoint
```bash
curl -s http://localhost:8001/health | python3 -m json.tool
# Expected:
# {
#     "status": "ok",
#     "version": "0.2.0",
#     "remotion": { "available": false, ... },  # false OK — ffmpeg stub
#     "persistence": { "backend": "duo", "pg_available": true }
# }
```

### 3.2 S1 step-by-step init
```bash
curl -s -X POST http://localhost:8001/scenario/s1/start \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ai_video_demo_2026" \
  -d '{
    "product_catalog": {"name": "Maternity Pillow", "usps": ["ergonomic", "breathable"]},
    "brand_guidelines": {"brand_name": "Momcozy"},
    "target_platforms": ["tiktok", "shopify"],
    "target_languages": ["en"],
    "week": "2026-W18",
    "video_duration": 30,
    "mode": "step_by_step"
  }' | python3 -m json.tool
# Expected: {"label": "s1_1XXXXXX...", "mode": "step_by_step", "status": "initialized", "current_step": null}
# Save label for later tests: LABEL=<returned label>
```

### 3.3 Frontend loads
Open http://localhost:3000 in browser.
Expected: Splash screen appears, then scene selector with DurationSlider shown above it. Nav component visible.
Note: DurationSelector now shows 5 tiers (Ultra Short 5-15s, Standard 15-30s, Extended 30-45s, Medium Long 45-60s, Long 60-90s). Toggle locale to verify i18n (CN/EN).

---

## 3a. i18n Smoke Test

### 3a.1 Toggle language switch
Click the locale toggle button in the nav bar. Expected: UI switches between Chinese and English. Repeat toggle both directions.

### 3a.2 Verify key screens in both languages
Check that all these screens display translated text in both CN and EN modes:
- Splash screen title and subtitle
- Scene selector labels and descriptions
- Duration slider labels (5 tiers: Ultra Short, Standard, Extended, Medium Long, Long)
- Step-by-step workflow step labels
- Review Panel headers and buttons
- Distribution view headers and buttons
- Asset Library headers and filters

### 3a.3 Verify no hardcoded Chinese text remains in components
```bash
cd /Users/pray/project/hermes_evo/AI_vedio/web/src
# Check for any hardcoded Chinese characters in component files
grep -rn '[\x{4e00}-\x{9fff}]' components/ app/
# Expected: zero matches (all text goes through t() calls)
```

---

## 4. Functional Tests -- S1 Auto Mode

### 4.1 Run full S1 auto pipeline
```bash
curl -s -X POST http://localhost:8001/scenario/s1 \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ai_video_demo_2026" \
  -d '{
    "product_catalog": {"name": "Maternity Pillow", "usps": ["ergonomic", "breathable"], "category": "pregnancy" },
    "brand_guidelines": {"brand_name": "Momcozy"},
    "target_platforms": ["tiktok", "shopify"],
    "target_languages": ["en"],
    "week": "2026-W18",
    "video_duration": 30
  }' > /tmp/s1_auto_result.json 2>&1

# Check result structure:
python3 -c "
import json
r = json.load(open('/tmp/s1_auto_result.json'))
print('success:', r.get('success'))
print('scenario:', r.get('scenario'))
print('steps_completed:', r.get('steps_completed'))
print('briefs:', len(r.get('briefs', [])))
print('scripts:', len(r.get('scripts', [])))
print('storyboards:', len(r.get('storyboards', [])))
print('keyframe_images:', len(r.get('keyframe_images', [])) if r.get('keyframe_images') else 0)
print('video_prompts:', len(r.get('video_prompts', [])))
print('clip_paths:', len(r.get('clip_paths', [])))
print('audio_paths:', len(r.get('audio_paths', [])))
print('thumbnail_image_paths:', len(r.get('thumbnail_image_paths', [])))
print('final_video_path:', r.get('final_video_path', ''))
print('audit_report status:', r.get('audit_report', {}).get('overall_status'))
print('errors:', r.get('errors', []))
print('media_errors:', r.get('media_synthesis_errors', []))
"
```
**Expected:** success=True, steps_completed=12, briefs>0, scripts>0, clip_paths>0,
audio_paths>0 (or 0 if ElevenLabs key missing), final_video_path non-empty,
audit_report has overall_status.

### 4.2 Verify generated files exist
```bash
# Check output directories
ls -la /Users/pray/project/hermes_evo/AI_vedio/output/seedance/ | head -10
ls -la /Users/pray/project/hermes_evo/AI_vedio/output/audio/ | head -10
ls -la /Users/pray/project/hermes_evo/AI_vedio/output/gpt_images/ | head -10
ls -la /Users/pray/project/hermes_evo/AI_vedio/output/renders/ | head -10
# Expected: .mp4 files in seedance/, .mp3 files in audio/, .png in gpt_images/
```

---

## 5. Functional Tests -- S1 Step-by-Step

### 5.1 Initialize step-by-step
Use the label from section 3.2 (or run the init again):
```bash
# Skip if already have label from 3.2; else run init first:
RESP=$(curl -s -X POST http://localhost:8001/scenario/s1/start \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ai_video_demo_2026" \
  -d '{"product_catalog":{"name":"Maternity Pillow","usps":["ergonomic","breathable"]},"brand_guidelines":{"brand_name":"Momcozy"},"target_platforms":["tiktok","shopify"],"target_languages":["en"],"week":"2026-W18","video_duration":30,"mode":"step_by_step"}')
LABEL=$(echo $RESP | python3 -c "import sys,json; print(json.load(sys.stdin)['label'])")
echo "LABEL=$LABEL"
```

### 5.2 Execute step: strategy
```bash
curl -s -X POST "http://localhost:8001/scenario/s1/step/strategy" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ai_video_demo_2026" \
  -d "{\"label\": \"$LABEL\"}" | python3 -m json.tool | head -30
# Expected: step="strategy", status="completed", data contains briefs
```

### 5.3 Execute step: scripts
```bash
curl -s -X POST "http://localhost:8001/scenario/s1/step/scripts" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ai_video_demo_2026" \
  -d "{\"label\": \"$LABEL\"}" | python3 -m json.tool | head -30
# Expected: step="scripts", status="completed", data contains scripts[]
```

### 5.4 Execute remaining steps (compliance, storyboards, keyframe_images, video_prompts, thumbnail_prompts, seedance_clips, tts_audio, thumbnail_images, assemble_final, audit)
```bash
for step in compliance storyboards keyframe_images video_prompts thumbnail_prompts seedance_clips tts_audio thumbnail_images assemble_final audit; do
  echo "--- Running step: $step ---"
  curl -s -X POST "http://localhost:8001/scenario/s1/step/$step" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: ai_video_demo_2026" \
    -d "{\"label\": \"$LABEL\"}" | python3 -c "import sys,json; d=json.load(sys.stdin); print('status:', d.get('status'), '| has_data:', d.get('data') is not None)"
done
# Expected: each step returns status="completed"
```

### 5.5 Edit a step output (e.g., edit the scripts output via PUT)
```bash
# First read current state to get step data:
curl -s "http://localhost:8001/scenario/s1/state/$LABEL" \
  -H "X-API-Key: ai_video_demo_2026" | python3 -c "
import sys, json
s = json.load(sys.stdin)
scripts = s.get('steps', {}).get('scripts', {})
print('scripts output exists:', scripts.get('output') is not None)
print('scripts status:', scripts.get('status'))
"

# Edit scripts step output:
curl -s -X PUT "http://localhost:8001/scenario/s1/state/$LABEL" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ai_video_demo_2026" \
  -d '{"steps": {"scripts": {"edited_output": [{"id": "S1-EDITED", "product_name": "Maternity Pillow", "segments": [{"segment_type": "hook", "description": "New hook!", "start_time": 0, "end_time": 5, "visual_description": "Edited product shot", "voiceover": "Try our new pillow!"}]}], "edited": true}}}' | python3 -m json.tool | head -10
# Expected: returns updated state. Verify "edited": true in scripts step.
```

### 5.6 Regenerate storyboard after editing scripts (downstream invalidation)
```bash
curl -s -X POST "http://localhost:8001/scenario/s1/regenerate" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ai_video_demo_2026" \
  -d "{\"label\": \"$LABEL\", \"step\": \"storyboards\"}" | python3 -m json.tool
# Expected: regenerated_step="storyboards", invalidated list contains all downstream steps
# (keyframe_images, video_prompts, thumbnail_prompts, seedance_clips, tts_audio, thumbnail_images, assemble_final, audit)
```

### 5.7 Verify downstream steps were invalidated
```bash
curl -s "http://localhost:8001/scenario/s1/state/$LABEL/steps?scenario=s1" \
  -H "X-API-Key: ai_video_demo_2026" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for s in d.get('steps', []):
    print(f\"{s['step_name']:25s} status={s['status']:10s} edited={s.get('is_edited')}\")
"
# Expected: storyboards is "done", all steps after it are "pending"
```

### 5.8 Resume from current step to completion
```bash
curl -s -X POST "http://localhost:8001/scenario/s1/resume" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ai_video_demo_2026" \
  -d "{\"label\": \"$LABEL\"}" | python3 -c "
import sys, json
d = json.load(sys.stdin)
steps = d.get('steps', {})
for k, v in steps.items():
    print(f'{k:25s} status={v.get(\"status\",\"?\")}')
print('errors:', d.get('errors', []))
"
# Expected: all steps show "done", no fatal errors
```

---

## 6. Functional Tests -- Persistence

### 6.1 Create state, kill backend, restart, verify
```bash
# First create a pipeline in progress
RESP=$(curl -s -X POST http://localhost:8001/scenario/s1/start \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ai_video_demo_2026" \
  -d '{"product_catalog":{"name":"Persistence Test Product","usps":["test"]},"brand_guidelines":{"brand_name":"TestBrand"},"target_platforms":["tiktok"],"target_languages":["en"],"week":"2026-W18","video_duration":15,"mode":"step_by_step"}')
PERSIST_LABEL=$(echo $RESP | python3 -c "import sys,json; print(json.load(sys.stdin)['label'])")
echo "PERSIST_LABEL=$PERSIST_LABEL"

# Execute first step
curl -s -X POST "http://localhost:8001/scenario/s1/step/strategy" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ai_video_demo_2026" \
  -d "{\"label\": \"$PERSIST_LABEL\"}" | python3 -c "import sys,json; print('strategy done:', json.load(sys.stdin).get('status'))"

# Kill backend (Ctrl+C in Terminal 1 or kill the uvicorn PID)
# Then restart:
cd /Users/pray/project/hermes_evo/AI_vedio && source .venv/bin/activate && uvicorn src.api:app --reload --port 8001 &

# Wait for restart:
sleep 3

# Verify state is preserved:
curl -s "http://localhost:8001/scenario/s1/state/$PERSIST_LABEL" \
  -H "X-API-Key: ai_video_demo_2026" | python3 -c "
import sys, json
s = json.load(sys.stdin)
steps = s.get('steps', {})
for k, v in steps.items():
    print(f'{k:25s} status={v.get(\"status\",\"?\")}')
"
# Expected: strategy is "done", all others are "pending" (state restored from PG)
```

### 6.2 Continue execution after restart
```bash
curl -s -X POST "http://localhost:8001/scenario/s1/step/scripts" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ai_video_demo_2026" \
  -d "{\"label\": \"$PERSIST_LABEL\"}" | python3 -c "import sys,json; print('scripts done:', json.load(sys.stdin).get('status'))"
# Expected: status="completed" (pipeline continues after restart)
```

### 6.3 Verify PG dual-write
```bash
docker exec ai_video_pg psql -U ai_video -d ai_video -c "SELECT count(*) FROM pipeline_state WHERE label LIKE 's1_%';"
# Expected: count > 0 (pipeline states stored in PostgreSQL)
```

---

## 7. Functional Tests -- S3 Pipeline

### 7.1 Run S3 influencer remix with video_duration
```bash
curl -s -X POST http://localhost:8001/scenario/s3 \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ai_video_demo_2026" \
  -d '{
    "video_url": "https://example.com/sample_influencer_video.mp4",
    "product": {"name": "Maternity Pillow", "usps": ["ergonomic", "breathable", "machine washable"]},
    "influencer_name": "Test Influencer",
    "video_duration": 30
  }' > /tmp/s3_result.json 2>&1

python3 -c "
import json
r = json.load(open('/tmp/s3_result.json'))
print('success:', r.get('success'))
print('video_analysis:', type(r.get('video_analysis')).__name__)
print('remix_script:', type(r.get('remix_script')).__name__)
print('clip_paths:', len(r.get('clip_paths', [])))
print('audio_paths:', len(r.get('audio_paths', [])))
print('final_video_path:', r.get('final_video_path', ''))
print('errors:', r.get('errors', []))
"
# Expected: success=True, clip_paths/audio_paths populated, final_video_path non-empty (or empty if Remotion fails)
# Note: S3 video_analysis may fail if sample URL is unreachable. Partial success accepted.
```

---

## 7a. S3 Influencer Remix with Quality Layer

### 7a.1 Run S3 pipeline with video_duration=30
```bash
curl -s -X POST http://localhost:8001/scenario/s3 \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ai_video_demo_2026" \
  -d '{
    "video_url": "https://example.com/sample_influencer_video.mp4",
    "product": {"name": "Maternity Pillow", "usps": ["ergonomic", "breathable", "machine washable"]},
    "influencer_name": "Test Influencer",
    "video_duration": 30
  }' > /tmp/s3_quality_result.json 2>&1

# Check success
python3 -c "
import json
r = json.load(open('/tmp/s3_quality_result.json'))
print('success:', r.get('success'))
print('scenario:', r.get('scenario'))
"
# Expected: success=True
```

### 7a.2 Verify identity_card appears in response
```bash
python3 -c "
import json
r = json.load(open('/tmp/s3_quality_result.json'))
ic = r.get('identity_card')
print('identity_card present:', ic is not None)
if ic:
    print('reference_frames:', len(ic.get('reference_frames', [])))
    print('face_count:', ic.get('attributes', {}).get('face_count'))
    print('face_quality_score:', ic.get('attributes', {}).get('face_quality_score'))
"
# Expected: identity_card is non-None, reference_frames >= 0 (may be empty if no faces detected),
# face_count >= 0, face_quality_score is a number
```

### 7a.3 Verify storyboard_with_keyframes has keyframe_image_path per shot
```bash
python3 -c "
import json
r = json.load(open('/tmp/s3_quality_result.json'))
sb = r.get('storyboard_with_keyframes', [])
print('storyboard_with_keyframes shots:', len(sb))
for i, shot in enumerate(sb[:3]):
    kp = shot.get('keyframe_image_path', '')
    print(f'  shot[{i}] keyframe_image_path: {\"SET\" if kp else \"EMPTY\"} -> {kp[:60] if kp else \"N/A\"}')
"
# Expected: storyboard_with_keyframes has 1+ shots, each with a non-empty keyframe_image_path
```

### 7a.4 Verify clip generation uses image_to_video mode (check logs)
```bash
# Fetch recent backend logs for image_to_video mode keyword
curl -s http://localhost:8001/health 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','UNKNOWN'))"

# Check if logs contain image_to_video references (requires log endpoint or journal)
# Option A: If a /logs endpoint exists:
curl -s http://localhost:8001/api/logs?q=image_to_video 2>/dev/null | python3 -c "
import sys,json
try:
    d = json.load(sys.stdin)
    logs = d if isinstance(d, list) else d.get('logs', [])
    matches = [l for l in logs if 'image_to_video' in str(l)]
    print(f'image_to_video log lines: {len(matches)}')
    for m in matches[:3]:
        print(f'  {str(m)[:120]}')
except Exception:
    print('No /api/logs endpoint available; check backend terminal output manually')
"

# Option B (manual): grep backend output for image_to_video
echo "Manual check: look for 'image_to_video' or 'image-to-video' in backend terminal output"
echo "Expected: log lines showing clip generation using image_to_video mode"
```

---

## 8. Regression Checks

### 8.1 Old pipeline endpoints still work
```bash
# Health endpoint
curl -s http://localhost:8001/health | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])"
# Expected: "ok"

# Old /pipeline/start (LangGraph-based)
curl -s -X POST http://localhost:8001/pipeline/start \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ai_video_demo_2026" \
  -d '{"product_catalog": {"name": "Test"}, "content_scenario": "influencer_remix"}' | python3 -m json.tool | head -10
# Expected: {"thread_id": "...", "status": "interrupted", ...}
```

### 8.2 S2 brand campaign endpoint
```bash
curl -s -X POST http://localhost:8001/scenario/s2 \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ai_video_demo_2026" \
  -d '{"brand_package": {"brand_name": "TestBrand"}, "target_platforms": ["tiktok"], "target_languages": ["en"], "week": "2026-W18"}' | python3 -c "import sys,json; d=json.load(sys.stdin); print('S2 success:', d.get('success'))"
# Expected: success=True (may have empty outputs, should not crash)
```

### 8.3 File serving
```bash
# List files
curl -s http://localhost:8001/api/files -H "X-API-Key: ai_video_demo_2026" | python3 -c "import sys,json; d=json.load(sys.stdin); print('files count:', len(d.get('files', [])))"
# Expected: returns array (may be empty)
```

---

## 9. Bug Watch List

| # | Issue | Risk | How to detect | Action if hit |
|---|-------|------|---------------|---------------|
| B1 | **Remotion binding** fails on current platform | High | `npx remotion --version` crashes | Accept ffmpeg stub fallback; note in results |
| B2 | **Seedance connectivity** -- 403 or HTTP/2 error | High | `clip_paths` empty, errors contain "seedance" | Stub clips already handled; note exact error |
| B3 | **PG connection** -- backend can't reach Docker PG | Medium | `/health` shows `pg_available: false` | Fallback to SQLite `DATABASE_URL=sqlite:///...` |
| B4 | **ElevenLabs key missing** -- TTS returns silent MP3 | Low | `audio_paths` empty, no crash | Pre-known issue; silent MP3 fallback works |
| B5 | **Step-by-step init** fails if `mode` not accepted | Medium | S1 start returns 500 | Check backend logs for `StepRunner.init_state` error |
| B6 | **State not found** after restart (PG loss) | Medium | `GET /state` returns 404 | Check PG container logs; verify `pipeline_state` table exists |
| B7 | **Frontend polling** shows disconnected banner | Low | Disconnected banner appears (t("app.backendDisconnected")) | Confirm uvicorn on port 8001; CORS origins include localhost:3000 |
| B8 | **Keyframe images** step fails (gpt-image-2 not available) | Medium | `keyframe_images` list empty; error in logs | Accept empty keyframes as non-blocking fallback |
| B9 | **S3 video analysis** hangs on unreachable URL | Medium | `POST /scenario/s3` times out | Use local sample video file; set timeout on curl |
| B10 | **Quality Dashboard** shows no data | Low | Frontend shows empty audit section | Verify audit step ran; check `audit_report` in state |
| B11 | **i18n key missing** -- t() returns raw key string | Medium | UI shows raw keys like "step.strategy" | Add missing key to translations.ts for both zh and en |

---

## 10. Results Template

| # | Test Name | Expected | Actual | Pass/Fail | Notes |
|---|-----------|----------|--------|-----------|-------|
| 3.1 | Health endpoint | status=ok, version=0.2.0 | | | |
| 3.2 | S1 step-by-step init | label, mode=step_by_step | | | |
| 3.3 | Frontend loads | SceneSelector + DurationSlider + Nav | | | |
| 3a.1 | Language toggle CN/EN | UI switches between both languages | | | |
| 3a.2 | Key screens translated | All sections display translated text | | | |
| 3a.3 | No hardcoded Chinese in components | grep returns zero matches | | | |
| 4.1 | S1 auto pipeline | success=True, steps=12 | | | |
| 4.2 | Generated files exist | .mp4 in seedance/, etc. | | | |
| 5.2 | Step strategy | status=completed, briefs>0 | | | |
| 5.3 | Step scripts | status=completed, scripts>0 | | | |
| 5.4 | All S1 steps sequential | Each status=completed | | | |
| 5.5 | Edit step output | state updated, edited=true | | | |
| 5.6 | Regenerate + invalidate | downstream all "pending" | | | |
| 5.8 | Resume from current step | all steps "done" | | | |
| 6.1 | Persist after restart | state restored, strategy "done" | | | |
| 6.2 | Continue after restart | scripts status=completed | | | |
| 6.3 | PG has stored states | count > 0 | | | |
| 7.1 | S3 remix with duration | success=True, clips>0 | | | |
| 8.1 | Old /pipeline/start | thread_id, status=interrupted | | | |
| 8.2 | S2 brand campaign | success=True | | | |
| 8.3 | File listing | returns file count | | | |

**Overall verdict:** (PASS / PARTIAL / FAIL) -- \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_
**Blockers found:** \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_
**Notes for tomorrow:** \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_
