# API Endpoint Reference

**Service:** Short Video Agent API (FastAPI)  
**Base URL:** `http://localhost:8001`  
**Version:** `0.2.0`  

## Authentication

The machine-readable public boundary is
`configs/backend-route-auth-contract.yaml`. Only these routes have a public or
specialized authentication entry:

- `GET /health` is unauthenticated for load-balancer and deployment health
  checks.
- `GET /metrics` is the Prometheus scrape endpoint; production exposure is
  controlled by the nginx/network layer.
- `GET /api/media/{media_path:path}` allows unsigned access only below the
  explicit `brand_assets` and `demo` roots. Every protected tenant path
  requires a scoped, expiring tenant-bound token.
- `POST /api/admin/auth/login` uses rate limiting and password verification to
  create the admin session and CSRF cookies.

Ordinary tenant/application routers require the `X-API-Key` header:

```
X-API-Key: <your-api-key>
```

Admin routes use the admin session rather than a tenant API key. Except for the
login route, every admin endpoint requires the session; every state-changing
admin request also requires the matching CSRF cookie/header contract.

The service fails fast when neither `API_KEY` nor an explicitly configured
development `TEST_BUNDLE_KEY` is available; it does not generate or log a
temporary credential.

The W1-27–W1-30 provider-cost ledger and per-job budget work adds no public HTTP
endpoint or caller-controlled budget field. Provider account/attempt readback,
operation scopes, recovery, and billing facts remain server-owned internal
contracts; Task 10 verification is local/fixture/disposable-database evidence
only and does not prove production migration or invoice reconciliation.

---

## Table of Contents

1. [Health & Diagnostics](#1-health--diagnostics)
2. [Pipeline -- S1 Product Direct](#2-pipeline--s1-product-direct)
3. [Pipeline -- Generic (all scenarios)](#3-pipeline--generic-all-scenarios)
4. [Pipeline -- S2 / S3 / S4](#4-pipeline--s2--s3--s4)
5. [Legacy Pipeline](#5-legacy-pipeline)
6. [Assets](#6-assets)
7. [Distribution](#7-distribution)
8. [Telemetry](#8-telemetry)
9. [File Upload & Media](#9-file-upload--media)
10. [Canonical Async Submission & Recovery](#10-canonical-async-submission--recovery)
11. [Artifact Acceptance Records](#11-artifact-acceptance-records)

---

## 1. Health & Diagnostics

### GET /health

No authentication required. Returns server health, version, Remotion status, and persistence backend info.

**Response:**
```json
{
  "status": "ok",
  "version": "0.2.0",
  "remotion": {
    "ffmpeg_available": true,
    "node_available": true,
    "remotion_bundle": true
  },
  "persistence": {
    "backend": "postgres",
    "status": "healthy",
    "pg_available": true
  }
}
```

**Key fields:**
- `status` -- `"ok"` if the server is running.
- `remotion` -- Object with booleans for `ffmpeg_available`, `node_available`, `remotion_bundle`.
- `persistence.backend` -- `"postgres"`, `"sqlite"`, or `"filesystem"`.
- `persistence.status` -- `"healthy"` or error description.

---

## 2. Pipeline -- S1 Product Direct

### POST /scenario/s1

Full-automatic S1 Product Direct pipeline. Runs end-to-end: strategy, scripts, storyboards, keyframes, video prompts, Seedance clips, TTS audio, thumbnails, final assembly, and audit.

**Headers:** `X-API-Key`

**Request body:**
```json
{
  "product_catalog": {
    "name": "Ergonomic Chair Pro",
    "brand_name": "ComfortCo",
    "description": "Premium ergonomic office chair with lumbar support",
    "usps": ["Adjustable lumbar support", "Breathable mesh back", "350 lb capacity"],
    "target_audience": "remote workers"
  },
  "brand_guidelines": {},
  "target_platforms": ["tiktok", "shopify"],
  "week": "2026-W18",
  "video_duration": 30
}
```

**Response:**
```json
{
  "success": true,
  "scenario": "product_direct",
  "brand_mode": false,
  "video_duration": 30,
  "errors": [],
  "media_synthesis_errors": [],
  "briefs": [...],
  "scripts": [...],
  "storyboards": [...],
  "keyframe_images": [...],
  "video_prompts": [...],
  "thumbnail_sets": [...],
  "clip_paths": ["output/seedance/clip1.mp4", ...],
  "audio_paths": ["output/audio/voiceover.mp3", ...],
  "thumbnail_image_paths": ["output/gpt_images/thumb1.png", ...],
  "final_video_path": "output/renders/final.mp4",
  "render_json_path": "output/renders/render.json",
  "audit_report": { "overall_status": "pass", ... },
  "steps_completed": 12
}
```

**Key fields:**
- `success` -- Boolean, `true` if pipeline completed without fatal errors.
- `briefs` / `scripts` -- Array of generated content briefs and scripts.
- `final_video_path` -- Path to the assembled output video (empty if media synthesis disabled).
- `audit_report.overall_status` -- `"pass"` or `"fail"`.
- `steps_completed` -- `7` (no media synthesis) or `12` (full pipeline).

---

### POST /scenario/s1/start

Initialize an S1 pipeline run in either `"auto"` (full automatic) or `"step_by_step"` mode.

**Headers:** `X-API-Key`

**Request body:**
```json
{
  "product_catalog": { ... },
  "brand_guidelines": {},
  "target_platforms": ["tiktok", "shopify"],
  "week": "2026-W18",
  "video_duration": 30,
  "mode": "step_by_step",
  "brand_mode": false
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `product_catalog` | object | required | Product details (name, usps, brand_name, etc.) |
| `brand_guidelines` | object | `{}` | Brand compliance rules |
| `target_platforms` | array | `["tiktok","shopify"]` | Target platforms |
| `week` | string | `""` | ISO week string, e.g. `"2026-W18"` |
| `video_duration` | int | `30` | Valid: 15, 30, 45, 60, 90 |
| `mode` | string | `"auto"` | `"auto"` or `"step_by_step"` |
| `brand_mode` | bool | `false` | Enable brand compliance audit (S2 behaviour) |

**Response (mode = `"step_by_step"`):**
```json
{
  "label": "s1_1714320000",
  "mode": "step_by_step",
  "status": "initialized",
  "current_step": null
}
```

**Response (mode = `"auto"`):** Same shape as `POST /scenario/s1` -- returns the completed pipeline result.

---

### POST /scenario/s1/step/{step_name}

Execute a single step of the S1 pipeline. Only valid when the pipeline was started in `"step_by_step"` mode.

**Headers:** `X-API-Key`

**Path parameter:** `step_name` -- one of: `strategy`, `scripts`, `compliance`, `storyboards`, `keyframe_images`, `video_prompts`, `thumbnail_prompts`, `seedance_clips`, `tts_audio`, `thumbnail_images`, `assemble_final`, `audit`.

**Request body:**
```json
{
  "label": "s1_1714320000"
}
```

**Response:**
```json
{
  "step": "scripts",
  "status": "completed",
  "cached": false,
  "data": { "...": "..." }
}
```

**Key fields:**
- `status` -- `"completed"` or `"failed"`.
- `cached` -- `true` if the step was already done and the cached result is returned.
- `data` -- The step output (structure varies by step).

---

### POST /scenario/s1/regenerate

Force re-execution of a specific step. Invalidates all downstream steps (marks them as `"pending"`) so they are re-run with updated input.

**Headers:** `X-API-Key`

**Request body:**
```json
{
  "label": "s1_1714320000",
  "step": "scripts"
}
```

**Response:**
```json
{
  "label": "s1_1714320000",
  "regenerated_step": "scripts",
  "invalidated": ["compliance", "storyboards", ...]
}
```

**Key fields:**
- `regenerated_step` -- The step that was re-executed.
- `invalidated` -- Array of downstream step names that were reset to `"pending"`.

---

### POST /scenario/s1/resume

Resume pipeline execution from the current step to completion. Used after editing step outputs.

**Headers:** `X-API-Key`

**Request body:**
```json
{
  "label": "s1_1714320000"
}
```

**Response:** Final pipeline state dict (same shape as `POST /scenario/s1` response).

---

### GET /scenario/s1/state/{label}

Get the current pipeline state for a given label.

**Headers:** `X-API-Key`

**Response:**
```json
{
  "label": "s1_1714320000",
  "scenario": "product_direct",
  "config": { ... },
  "steps": {
    "strategy": { "status": "done", "output": [...], "completed_at": "..." },
    "scripts": { "status": "done", "output": [...], "completed_at": "..." }
  },
  "current_step": "storyboards",
  "mode": "step_by_step",
  "errors": [],
  "media_synthesis_errors": []
}
```

Returns `404` if the label does not exist.

---

### PUT /scenario/s1/state/{label}

Update/edit the pipeline state. Used after a tester or reviewer edits a step's output. Deep-merges the request body into the saved state.

**Headers:** `X-API-Key`

**Request body:**
```json
{
  "steps": {
    "scripts": {
      "edited_output": { "edited": "script content here..." },
      "edited": true
    }
  }
}
```

Common use case: set `{ "steps": { "<step_name>": { "edited_output": {...}, "edited": true } } }`.

**Response:** The full merged state dict (same shape as `GET /scenario/s1/state/{label}`).

Returns `404` if the label does not exist.

---

## 3. Pipeline -- Generic (all scenarios)

### GET /scenario/{scenario}/state/{label}/steps

List all pipeline steps with their status, preview, and completion timestamps.

**Headers:** `X-API-Key`

**Path parameters:**
- `scenario` -- Scenario identifier (currently only `"s1"`).
- `label` -- Pipeline run label.

**Response:**
```json
{
  "label": "s1_1714320000",
  "scenario": "s1",
  "current_step": "scripts",
  "steps": [
    {
      "step_name": "strategy",
      "status": "done",
      "preview": "[3 items]",
      "has_output": true,
      "is_edited": false,
      "completed_at": "2026-04-28T10:00:00"
    },
    {
      "step_name": "scripts",
      "status": "done",
      "preview": "script content preview...",
      "has_output": true,
      "is_edited": true,
      "completed_at": "2026-04-28T10:05:00"
    },
    {
      "step_name": "compliance",
      "status": "pending",
      "preview": "",
      "has_output": false,
      "is_edited": false,
      "completed_at": ""
    }
  ]
}
```

**Key fields:**
- `current_step` -- The step currently being executed or the next to be run.
- `steps[].status` -- `"pending"`, `"running"`, `"done"`, or `"failed"`.
- `steps[].preview` -- Brief text preview of the step output (truncated to 80 chars).
- `steps[].has_output` -- Boolean, whether the step has produced output data.
- `steps[].is_edited` -- Boolean, whether the step output has been manually edited.

---

### POST /scenario/{scenario}/step/{step_name}

Execute a single pipeline step. Validates that all prerequisite steps are complete before executing. Returns cached result if the step is already completed.

**Headers:** `X-API-Key`

**Path parameters:**
- `scenario` -- Currently only `"s1"`.
- `step_name` -- One of the valid step names.

**Request body:**
```json
{
  "label": "s1_1714320000"
}
```

**Response (success):**
```json
{
  "step": "scripts",
  "status": "completed",
  "cached": false,
  "data": { "...": "..." }
}
```

**Response (missing dependencies -- 400):**
```json
{
  "detail": {
    "message": "Cannot execute 'scripts': prior steps not complete",
    "missing_deps": [
      { "step": "strategy", "status": "pending" }
    ]
  }
}
```

Returns `400` if the step has incomplete dependencies. Returns `404` if the label is not found.

---

### PUT /scenario/{scenario}/state/{label}

Update the state for a specific step's output (allows user editing of step results).

**Headers:** `X-API-Key`

**Request body:**
```json
{
  "step_name": "scripts",
  "updates": { "edited_script": "New script content..." }
}
```

**Response:**
```json
{
  "label": "s1_1714320000",
  "updated_step": "scripts",
  "state": { "...": "full updated state..." }
}
```

Returns `400` if `step_name` or `updates` is missing. Returns `404` if the label is not found.

---

### POST /scenario/{scenario}/regenerate/{label}/{step_name}

Re-run a specific step after the user edited its input. Invalidates all downstream steps so they are re-executed.

**Headers:** `X-API-Key`

**Path parameters:**
- `scenario` -- `"s1"` / `"s2"` / `"s3"` / `"s4"` / `"s5"`.
- `label` -- Pipeline run label.
- `step_name` -- Step to regenerate.

**Response:**
```json
{
  "label": "s1_1714320000",
  "regenerated_step": "scripts",
  "invalidated": ["compliance", "storyboards", "keyframe_images", "video_prompts", "thumbnail_prompts", "seedance_clips", "tts_audio", "thumbnail_images", "assemble_final", "audit"]
}
```

**Key fields:**
- `regenerated_step` -- The step that was re-executed.
- `invalidated` -- Array of downstream steps that were reset to `"pending"`.

Notes:
- Downstream invalidation now follows the persisted state's scenario-specific step order.
- For `s4` / `s5`, this includes `continuity_storyboard_grid` where applicable instead of using the legacy S1-only chain.

---

## 4. Pipeline -- S2 / S3 / S4

### POST /scenario/s2

Run the S2 Brand Campaign pipeline. Generates a brand campaign video from a brand asset package.

**Headers:** `X-API-Key`

**Request body:**
```json
{
  "brand_package": {
    "brand_name": "ComfortCo",
    "logo_url": "https://cdn.example.com/logo.png",
    "colors": [
      { "name": "Primary Blue", "hex": "#1a73e8", "usage": "primary" }
    ],
    "fonts": [
      { "name": "Heading", "family": "Inter", "weights": ["regular", "bold"] }
    ],
    "intro_video_id": "ASSET-ABCD1234",
    "outro_video_id": "ASSET-EFGH5678",
    "tone_of_voice": "Professional and inspiring",
    "target_audience": "Remote workers"
  },
  "target_platforms": ["tiktok", "shopify"],
  "target_languages": ["en"],
  "week": "2026-W18"
}
```

**Response:** Same shape as `POST /scenario/s1` with `brand_mode: true` -- includes `compliance_reports` array and a `steps_completed` of up to 12.

---

### POST /scenario/s3

Run the S3 Influencer Remix pipeline. Takes an influencer video URL + product info and produces a remix video preserving the influencer's style.

**Headers:** `X-API-Key`

**Request body:**
```json
{
  "video_url": "https://tiktok.com/@user/video/123",
  "product": {
    "name": "X1 Pump",
    "usps": ["Quiet operation", "Portable design"],
    "brand_name": "LactFit"
  },
  "influencer_name": "Jessica",
  "brief_id": "RMX-ABC12345",
  "video_duration": 30
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `video_url` | string | required | URL of the influencer's original video |
| `product` | object | required | Product info (name, usps, brand_name) |
| `influencer_name` | string | `"Influencer"` | Display name for the influencer |
| `brief_id` | string | `""` | Optional pre-created remix brief ID |
| `video_duration` | int | `30` | Valid: 15, 30, 45, 60, 90 |

**Response:**
```json
{
  "success": true,
  "video_analysis": { "hook_type": "pain_point", "speech_style": "casual", ... },
  "identity_card": { "name": "Jessica", "style_tags": [...], ... },
  "remix_script": { "segments": [...], "full_script": "...", ... },
  "storyboard_with_keyframes": { ... },
  "video_prompts": [{"prompt": "...", "duration": 10}, ...],
  "thumbnail_sets": [{"prompt": "...", "style": "..."}, ...],
  "clip_paths": ["output/seedance/clip1.mp4", ...],
  "audio_paths": ["output/audio/remix_voice.mp3", ...],
  "thumbnail_image_paths": ["output/gpt_images/thumb1.png", ...],
  "final_video_path": "output/renders/remix_final.mp4",
  "audit_report": { "overall_status": "pass", ... },
  "media_synthesis_errors": [],
  "errors": [],
  "segment_count": 4
}
```

**Key fields:**
- `video_analysis` -- Extracted style analysis from the original video.
- `remix_script` -- Style-preserving product script with segments.
- `segment_count` -- Number of script segments in the remix.
- `final_video_path` -- Path to the final assembled remix video.

---

### POST /scenario/s4

Run the S4 Live Shoot to Video pipeline. Produces a video from raw footage assets and product information.

**Headers:** `X-API-Key`

**Request body:**
```json
{
  "footage_assets": [
    {"path": "output/uploads/footage1.mp4", "type": "broll"},
    {"path": "output/uploads/footage2.mp4", "type": "talking_head"}
  ],
  "product_info": {
    "name": "Ergonomic Chair Pro",
    "brand_name": "ComfortCo"
  },
  "topic": "Office ergonomics tips",
  "target_platforms": ["tiktok"]
}
```

**Response:** Pipeline output dict (structure varies by S4 implementation).

---

## 5. Legacy Pipeline

`/pipeline/*` is an S1 Product Direct compatibility layer. New UI flows use
`/scenario/*` and StepRunner directly. Legacy S1 callers can keep using
`/pipeline/*`; S2-S5 callers must use `POST /scenario/{scenario}/submit`.
The compatibility router proxies to StepRunner instead of resuming the original
LangGraph checkpoint graph.

### POST /pipeline/start

Start a StepRunner-backed legacy pipeline run. Returns a synthetic `thread_id`
for tracking and starts execution in the background. Chinese product inputs are
translated to English before state initialization.

**Headers:** `X-API-Key`

**Request body:**
```json
{
  "product_catalog": {
    "name": "Ergonomic Chair Pro",
    "brand_name": "ComfortCo",
    "description": "High-end ergonomic chair",
    "usps": ["Lumbar support", "Breathable mesh"]
  },
  "brand_guidelines": {},
  "target_platforms": ["shopify", "amazon", "tiktok", "reddit"],
  "target_languages": ["en"],
  "content_calendar_week": "2026-W18",
  "content_scenario": "product_direct",
  "enable_media_synthesis": false,
  "artifact_disposition": "pending_review",
  "provider_max_retries": 0,
  "api_keys": {
    "openai": "sk-...",
    "elevenlabs": "..."
  }
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `content_scenario` | string | `"product_direct"` | Only `"product_direct"` and `"s1"` are supported by this S1-shaped legacy contract. Other scenarios return `422`. |
| `enable_media_synthesis` | strict boolean | `false` | Request intent/config defaults to no-media. Until the Task 4 execution guard is present, this field alone is not runtime proof that later media steps cannot run. |
| `artifact_disposition` | string | `"pending_review"` | Only `pending_review` or `quarantine`. |
| `provider_max_retries` | strict integer | `0` | Mutation retry is fixed at zero until durable idempotency exists. |
| `api_keys` | object | `{}` | Optional request-scoped provider keys; they are not written to process-wide environment variables. |

The authenticated API key must carry `provider:submit` or `all`, including a
no-media request because S1 strategy/script steps still invoke a text provider.
Client-supplied tenant, effective-policy, budget, approval, publish, delivery,
or transparency authority fields are rejected with `422`.

**Response:**
```json
{
  "thread_id": "c02687fa-ea8e-4d0e-94c4-dde4ab2a4b1d",
  "status": "started",
  "label": "s1_20260531_010000",
  "events": []
}
```

**Key fields:**
- `thread_id` -- Synthetic UUID used by legacy callers.
- `label` -- StepRunner state label mapped to the synthetic thread.
- `status` -- `"started"` after the background StepRunner resume task is registered.

---

### GET /pipeline/{thread_id}/state

Get the current state of a legacy pipeline run.

**Headers:** `X-API-Key`

**Response:**
```json
{
  "thread_id": "a1b2c3d4",
  "status": "interrupted",
  "current_review": "strategy_review",
  "pipeline_complete": false,
  "state": { "product_catalog": {...}, "human_reviews": {...}, ... }
}
```

**Key fields:**
- `status` -- `"interrupted"` (awaiting review), `"complete"`, `"not_found"`, or `"error"`.
- `current_review` -- Best-effort compatibility value. StepRunner does not use LangGraph checkpoint reviews.
- `state` -- StepRunner state converted to legacy field names. The pinned compatibility fields are `product_catalog`, `brand_guidelines`, `target_platforms`, `target_languages`, `content_calendar_week`, `content_scenario`, `current_step`, `errors`, `structured_errors`, `pipeline_complete`, `human_reviews`, `distribution_plans`, `analytics_reports`, `briefs`, `scripts`, `compliance_report`, `storyboards`, `keyframe_images`, `video_prompts`, `thumbnail_sets`, `seedance_output`, `audio_paths`, `thumbnail_image_paths`, `final_video_path`, and `audit_report`.

---

### POST /pipeline/{thread_id}/review/{review_node}

Submit a legacy human review decision. In the current StepRunner architecture
this endpoint is a no-op kept for backwards compatibility; all actions return
`"idempotent_skip"`. Use `/scenario/{s}/gate/{label}/{gate_id}/approve` for
the live gate approval path.

**Headers:** `X-API-Key`

**Path parameters:**
- `review_node` -- `"strategy_review"`, `"script_review"`, `"edit_review"`, `"thumbnail_review"`.

**Request body:**
```json
{
  "action": "approve",
  "reviewer_notes": "The strategy looks good, proceed to scripting."
}
```

| Field | Type | Description |
|-------|------|-------------|
| `action` | string | `"approve"`, `"reject"`, or `"request_changes"` |
| `reviewer_notes` | string | Optional notes from the reviewer |

**Response:**
```json
{
  "thread_id": "c02687fa-ea8e-4d0e-94c4-dde4ab2a4b1d",
  "review_node": "strategy_review",
  "action": "approve",
  "status": "idempotent_skip",
  "message": "StepRunner pipelines do not use checkpoint reviews. Use /scenario/{s}/gate/{label}/{gate_id}/approve for gate approval.",
  "events": []
}
```

**Key fields:**
- `status` -- Always `"idempotent_skip"` in StepRunner-backed `/pipeline/*` proxy mode.
- `action` -- Echoes the submitted action, including unknown legacy values.

---

### GET /pipeline/{thread_id}/distribution

Get distribution plans from a completed or in-progress legacy pipeline run.

**Headers:** `X-API-Key`

**Response:**
```json
{
  "distribution_plans": [
    {
      "brief_id": "BRIEF-001",
      "script_id": "SCRIPT-001",
      "platform_posts": {
        "shopify": { "body": "...", "cta": "Shop Now", "video_format": "mp4" },
        "amazon": { "body": "...", "cta": "Buy on Amazon" },
        "tiktok": { "body": "...", "cta": "Follow for more", "video_format": "mp4" },
        "reddit": { "body": "...", "cta": "Learn more" }
      }
    }
  ]
}
```

Returns `404` if thread not found. Returns an empty list when the StepRunner
state has not produced `assemble_final.output.distribution_plans`.

---

### GET /pipeline/{thread_id}/output

Get the full pipeline output (all state values) as JSON.

**Headers:** `X-API-Key`

**Response:** Full serialized pipeline state dict. Returns `404` if thread not found.

---

### GET /pipeline/{thread_id}/export

Clean export of pipeline output -- only user-facing fields. Strips internal state (`retry_counts`, `self_verifications`, `pipeline_metrics`, `errors`, etc.) and adds a `human_review_summary`.

**Headers:** `X-API-Key`

**Response:**
```json
{
  "product_catalog": {...},
  "brand_guidelines": {...},
  "target_platforms": [...],
  "distribution_plans": [...],
  "scripts": [...],
  "captions": [...],
  "thumbnails": [...],
  "analytics_reports": [...],
  "human_review_summary": [
    { "node": "strategy_review", "status": "approved", "notes": "Looks good" },
    { "node": "script_review", "status": "changes_requested", "notes": "Tone is too formal" }
  ]
}
```

**Key fields:**
- `human_review_summary` -- Array of `{node, status, notes}` for each review checkpoint.
- Internal fields (`retry_counts`, `self_verifications`, `rejection_feedback`, `pipeline_metrics`, `messages`, `errors`, `structured_errors`, `current_step`, `pipeline_complete`) are excluded.

---

## 6. Assets

> **Note:** All asset endpoints are mounted under the `/api/assets` prefix via an `APIRouter`. The router is conditionally included; `python-multipart` must be installed for `POST /api/assets/upload` to work.

### GET /api/files

List all media files across `uploads/`, `seedance/`, `audio/`, `gpt_images/`, `renders/`, `demo/` directories.

**Headers:** `X-API-Key`

**Response:**
```json
{
  "files": [
    {
      "filename": "clip1.mp4",
      "path": "/api/media/clip1.mp4",
      "size": 1048576,
      "type": "video",
      "created": 1714320000.0
    },
    {
      "filename": "thumbnail.png",
      "path": "/api/media/thumbnail.png",
      "size": 256000,
      "type": "image",
      "created": 1714319000.0
    }
  ]
}
```

**Key fields:**
- `type` -- `"video"`, `"image"`, `"audio"`, or `"document"` (inferred from extension).
- `created` -- Unix timestamp of file creation time.
- Sorted by creation time, newest first. Duplicate filenames are deduplicated.

---

### GET /api/media/{filename}

Serve a media file (video, audio, image) directly. Does **not** require the `X-API-Key` header.

Searches `OUTPUT_DIR` and `uploads/`, `seedance/`, `audio/`, `gpt_images/`, `renders/`, `demo/` subdirectories.

Returns the file with the correct `Content-Type` header based on extension. Returns `404` if not found.

---

### POST /api/assets/upload

Upload a video or image asset. Stores the file and returns an `asset_id` for pipeline use.

**Headers:** `X-API-Key`, `Content-Type: multipart/form-data`

**Request (multipart/form-data):**
| Field | Type | Description |
|-------|------|-------------|
| `file` | file (binary) | Video (.mp4, .mov, .webm) or image (.jpg, .png, .gif, .webp) |
| `tags` | string | Comma-separated tags (e.g. `"product,demo,lifestyle"`) |
| `metadata` | string | JSON string with arbitrary metadata (e.g. `'{"creator":"tester"}'`) |

**Response:**
```json
{
  "asset_id": "ASSET-ABCD1234",
  "filename": "ASSET-ABCD1234.mp4",
  "original_name": "product_demo.mp4",
  "file_path": "/output/assets/ASSET-ABCD1234/ASSET-ABCD1234.mp4",
  "file_size": 5242880,
  "mime_type": "video/mp4",
  "tags": ["product", "demo"],
  "metadata": {}
}
```

**Key fields:**
- `asset_id` -- Unique asset identifier (format: `ASSET-XXXXXXXX`).
- `file_path` -- Local filesystem path where the file is stored.
- `mime_type` -- Inferred from file extension.

---

### GET /api/assets/

List all stored asset records, optionally filtered by tags.

**Headers:** `X-API-Key`

**Query parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tags` | string | `""` | Comma-separated tags to filter by (AND logic) |
| `limit` | int | `100` | Maximum number of records to return |

**Response:**
```json
{
  "assets": [
    {
      "asset_id": "ASSET-ABCD1234",
      "filename": "ASSET-ABCD1234.mp4",
      "original_name": "product_demo.mp4",
      "file_path": "/output/assets/ASSET-ABCD1234/ASSET-ABCD1234.mp4",
      "file_size": 5242880,
      "mime_type": "video/mp4",
      "tags": ["product", "demo"],
      "metadata": {}
    }
  ],
  "total": 1
}
```

---

### GET /api/assets/{asset_id}

Get metadata for a single asset by ID.

**Headers:** `X-API-Key`

**Response:** Single `AssetRecord` dict (same shape as the list item above). Returns `404` if not found.

---

### DELETE /api/assets/{asset_id}

Delete an asset by ID. Removes the file and the metadata index entry.

**Headers:** `X-API-Key`

**Response:**
```json
{
  "deleted": true
}
```

Returns `404` if asset not found.

---

### PUT /api/assets/{asset_id}/tags

Update the tags for an existing asset. Replaces all existing tags.

**Headers:** `X-API-Key`

**Request body:**
```json
{
  "tags": ["product", "b-roll", "lifestyle"]
}
```

**Response:** Updated `AssetRecord` dict. Returns `404` if asset not found.

---

### GET /api/assets/brand-packages

List all brand asset packages.

**Headers:** `X-API-Key`

**Response:**
```json
{
  "packages": [
    {
      "package_id": "BPKG-ABCD1234",
      "brand_name": "ComfortCo",
      "description": "Office furniture brand",
      "logo_url": "https://cdn.example.com/logo.png",
      "logo_alt_text": "ComfortCo logo",
      "colors": [
        { "name": "Primary Blue", "hex": "#1a73e8", "usage": "primary" }
      ],
      "fonts": [
        { "name": "Heading", "family": "Inter", "weights": ["regular", "bold"] }
      ],
      "intro_video_id": "ASSET-ABCD1234",
      "outro_video_id": "ASSET-EFGH5678",
      "intro_duration_seconds": 3.0,
      "outro_duration_seconds": 3.0,
      "tone_of_voice": "Professional and inspiring",
      "forbidden_content": ["competitor references", "unsubstantiated claims"],
      "target_audience": "Remote workers",
      "selected_asset_ids": ["ASSET-AAAA", "ASSET-BBBB"],
      "created_at": "2026-04-28T10:00:00",
      "updated_at": "2026-04-28T10:00:00"
    }
  ],
  "total": 1
}
```

---

### POST /api/assets/brand-packages

Create a new brand asset package.

**Headers:** `X-API-Key`

**Request body:**
```json
{
  "brand_name": "ComfortCo",
  "description": "Office furniture brand",
  "logo_url": "https://cdn.example.com/logo.png",
  "logo_alt_text": "ComfortCo logo",
  "colors": [
    { "name": "Primary Blue", "hex": "#1a73e8", "usage": "primary" }
  ],
  "fonts": [
    { "name": "Heading", "family": "Inter", "weights": ["regular", "bold"] }
  ],
  "intro_video_id": "ASSET-ABCD1234",
  "outro_video_id": "ASSET-EFGH5678",
  "intro_duration_seconds": 3.0,
  "outro_duration_seconds": 3.0,
  "tone_of_voice": "Professional and inspiring",
  "forbidden_content": ["competitor references"],
  "target_audience": "Remote workers",
  "selected_asset_ids": ["ASSET-AAAA", "ASSET-BBBB"]
}
```

**Response:** The created `BrandAssetPackage` (same shape as the list item above), with auto-generated `package_id` (`BPKG-XXXXXXXX`) and timestamps.

---

### GET /api/assets/brand-packages/{package_id}

Get a single brand asset package by ID.

**Headers:** `X-API-Key`

**Response:** `BrandAssetPackage` dict. Returns `404` if not found.

---

### PUT /api/assets/brand-packages/{package_id}

Not implemented. Brand packages are immutable after creation; delete and re-create to update.

---

### DELETE /api/assets/brand-packages/{package_id}

Delete a brand asset package by ID.

**Headers:** `X-API-Key`

**Response:**
```json
{
  "deleted": true
}
```

Returns `404` if not found.

---

### GET /api/assets/influencers

List all registered influencer profiles.

**Headers:** `X-API-Key`

**Response:**
```json
{
  "influencers": [
    {
      "influencer_id": "INFL-ABCD1234",
      "name": "Jessica",
      "handle": "@jessica_reviews",
      "platforms": ["tiktok", "instagram"],
      "style_tags": ["unboxing", "review"],
      "style_profile": {
        "hook_type": "pain_point",
        "avg_speech_speed": 3.2,
        "speech_style": "casual",
        "catchphrases": ["let's be real"],
        "common_hooks": ["Ever had this problem?"],
        "emotion_curve": [
          { "time": 0, "emotion": "curious", "intensity": 0.7 }
        ],
        "structure_segments": [
          { "type": "hook", "start": 0, "end": 5, "description": "Grab attention" }
        ],
        "notes": "Authentic, relatable style"
      },
      "product_links": [
        {
          "product_id": "PROD-001",
          "product_name": "X1 Pump",
          "platform_specific_urls": { "shopify": "https://shop.com/x1" },
          "commission_rate": 0.15,
          "is_active": true
        }
      ],
      "recent_video_urls": ["https://tiktok.com/@jessica/video/1"],
      "notes": "Signed Q1 2026",
      "is_active": true,
      "created_at": "2026-04-28T10:00:00",
      "updated_at": "2026-04-28T10:00:00"
    }
  ],
  "total": 1
}
```

---

### POST /api/assets/influencers

Register a new influencer profile.

**Headers:** `X-API-Key`

**Request body:**
```json
{
  "name": "Jessica",
  "handle": "@jessica_reviews",
  "platforms": ["tiktok", "instagram"],
  "style_tags": ["unboxing", "review"],
  "style_profile": {
    "hook_type": "pain_point",
    "avg_speech_speed": 3.2,
    "speech_style": "casual",
    "catchphrases": ["let's be real"],
    "notes": "Authentic, relatable style"
  },
  "product_links": [
    {
      "product_id": "PROD-001",
      "product_name": "X1 Pump",
      "platform_specific_urls": { "shopify": "https://shop.com/x1" },
      "commission_rate": 0.15
    }
  ],
  "recent_video_urls": ["https://tiktok.com/@jessica/video/1"],
  "notes": "Signed Q1 2026",
  "is_active": true
}
```

**Response:** The created `InfluencerProfile` (same shape as the list item above), with auto-generated `influencer_id` (`INFL-XXXXXXXX`) and timestamps.

---

### GET /api/assets/influencers/{influencer_id}

Get a single influencer profile by ID.

**Headers:** `X-API-Key`

**Response:** `InfluencerProfile` dict. Returns `404` if not found.

---

### PUT /api/assets/influencers/{influencer_id}/product-links

Update an influencer's product links. Replaces all existing product links.

**Headers:** `X-API-Key`

**Request body:**
```json
[
  {
    "product_id": "PROD-001",
    "product_name": "X1 Pump",
    "platform_specific_urls": { "shopify": "https://shop.com/x1", "amazon": "https://amazon.com/x1" },
    "commission_rate": 0.15,
    "is_active": true
  }
]
```

**Response:** Updated `InfluencerProfile` dict. Returns `404` if influencer not found.

---

### DELETE /api/assets/influencers/{influencer_id}

Delete an influencer profile by ID.

**Headers:** `X-API-Key`

**Response:**
```json
{
  "deleted": true
}
```

Returns `404` if not found.

---

### POST /api/assets/remix-brief

Create an influencer remix brief. Triggers the S3 pipeline for a specific influencer + product.

**Headers:** `X-API-Key`

**Request body:**
```json
{
  "influencer_id": "INFL-ABCD1234",
  "original_video_url": "https://tiktok.com/@user/video/123",
  "product_id": "PROD-001",
  "product_name": "X1 Pump",
  "product_image_url": "https://cdn.example.com/x1.png",
  "product_link": "https://shop.com/x1",
  "commission_rate": 0.15,
  "target_platforms": ["tiktok"],
  "notes": "Focus on portability feature"
}
```

**Response:**
```json
{
  "brief_id": "RMX-ABCD1234",
  "influencer_id": "INFL-ABCD1234",
  "original_video_url": "https://tiktok.com/@user/video/123",
  "product_id": "PROD-001",
  "product_name": "X1 Pump",
  "product_image_url": "https://cdn.example.com/x1.png",
  "product_link": "https://shop.com/x1",
  "commission_rate": 0.15,
  "target_platforms": ["tiktok"],
  "notes": "Focus on portability feature"
}
```

---

## 7. Distribution

### GET /distribution/platforms

List available distribution platforms and their connection status.

**Headers:** `X-API-Key`

**Response:**
```json
[
  { "id": "tiktok", "name": "TikTok", "connected": true },
  { "id": "shopify", "name": "Shopify", "connected": true }
]
```

---

### POST /distribution/publish

Canonical acceptance-bound publish for exactly one TikTok or Shopify attempt.
The authenticated key must carry `artifact:publish` or `all`;
`artifact:accept` alone and `provider:submit` alone receive `403`.

**Headers:** `X-API-Key`

**Request body:**
```json
{
  "acceptance_id": "3f4b5088-4138-47c6-96ae-c918b8297010",
  "platform": "tiktok",
  "metadata": {
    "title": "Approved campaign video",
    "description": "One acceptance-bound publish attempt",
    "hook": "A reviewed opening line",
    "product_name": "Product name",
    "hashtags": ["approved", "campaign"],
    "tags": []
  },
  "platform_options": {
    "platform": "tiktok",
    "privacy_level": "SELF_ONLY",
    "disable_comment": true,
    "disable_duet": true,
    "disable_stitch": true,
    "brand_content_toggle": false,
    "brand_organic_toggle": true
  }
}
```

`acceptance_id` must be an exact lowercase UUID4. `platform` is exactly
`tiktok` or `shopify`. `platform_options` is required, strict, and must carry
the same platform discriminator. TikTok requires an allowed privacy value,
five exact booleans, and explicit commercial toggles; the server always sends
the AI-content label. Shopify accepts only an exact positive
`gid://shopify/Product/<id>` as `product_id`. `metadata` is required and strict;
its allowed fields are `title`, `description`, `hook`, `product_name`,
`hashtags`, and `tags`. Extra fields, client artifact paths, human-approval
objects, multi-platform arrays, null text, unsafe URLs/control characters, and
oversized metadata are rejected with sanitized `422` details. There is no
silent compatibility default for missing platform options.

**Response:**
```json
{
  "publish_attempt_id": "91ec3593-cc3c-42bf-99ee-c98655c5826b",
  "acceptance_id": "3f4b5088-4138-47c6-96ae-c918b8297010",
  "platform": "tiktok",
  "status": "published",
  "success": true,
  "post_id": "1234567890123456789",
  "post_url": "https://www.tiktok.com/@brand/video/1234567890123456789",
  "receipt": {
    "schema_version": "publish-receipt.v1",
    "platform": "tiktok",
    "protocol_version": "tiktok-content-posting-v2",
    "completion_scope": "tiktok_direct_post",
    "provider_operation_id": "v_pub_file_20260714_01",
    "provider_resource_id": "1234567890123456789",
    "target_id": null,
    "provider_status": "PUBLISH_COMPLETE",
    "post_id": "1234567890123456789",
    "post_url": "https://www.tiktok.com/@brand/video/1234567890123456789",
    "public_visibility_verified": true,
    "observed_at": "2026-07-14T08:00:00Z",
    "verified_by": "video_query",
    "simulated": false
  },
  "acceptance_consumed": true,
  "retry_allowed": false
}
```

**Key fields:**
- `publish_attempt_id` -- Server-generated durable attempt UUID4.
- `post_id` / `post_url` -- Bounded safe platform projection; either may be
  null when the receipt has no corresponding value. Shopify always returns
  both as null because product-media association is not public-post proof.
- `receipt` -- Strict `publish-receipt.v1`; every newly written published
  attempt must have one. TikTok operation ID is never projected as a post ID.
- `acceptance_consumed=true` -- This attempt consumed the W1-22 authority.
- `retry_allowed=false` -- Success never authorizes reuse of the acceptance.

### POST /publish/{video_id} (deprecated)

Compatibility adapter for the same strict request, response, permission, and
shared service as `POST /distribution/publish`. The bounded `video_id` path is
not authority and is not forwarded to the connector. All controlled legacy
responses include:

```http
Deprecation: true
Link: </distribution/publish>; rel="successor-version"
```

Clients should migrate to the canonical route. The adapter does not accept the
historical `content.video_path` or body `delivery_acceptance` shape.

### Stable publish errors

Both adapters declare the same response statuses:

| HTTP | Contract |
|---:|---|
| `200` | One strict published response object. |
| `401` | Missing/invalid API key; auth runs before body/path parsing. |
| `403` | Principal lacks `artifact:publish|all`. |
| `404` / `409` / `500` / `502` / `503` | Typed stable publish error detail below. |
| `422` | Sanitized JSON/body/path validation using only `type`, `loc`, and `msg`. |

Publish errors use this bounded detail shape:

```json
{
  "detail": {
    "code": "publish_connector_failed",
    "publish_attempt_id": "91ec3593-cc3c-42bf-99ee-c98655c5826b",
    "acceptance_consumed": true,
    "retry_allowed": false
  }
}
```

| HTTP | Stable code | Meaning |
|---:|---|---|
| `404` | `acceptance_not_found` | Tenant-safe acceptance lookup failed. |
| `409` | `acceptance_expired` | Acceptance expired before consume. |
| `409` | `acceptance_not_available` | Rejected, revoked, consumed, or concurrent loser. |
| `409` | `acceptance_artifact_integrity_mismatch` | Accepted bytes changed or disappeared. |
| `409` | `publish_preflight_rejected` | A trusted read-only platform response deterministically rejected current options, media, product, or scopes; acceptance remains unconsumed. |
| `503` | `acceptance_store_unavailable` | Inspection proved not consumed; only an explicit later request may proceed. |
| `503` | `publish_connector_not_ready` | Known mock/missing configuration before attempt. |
| `503` | `publish_attempt_store_unavailable` | Durable `prepared` insert failed. |
| `500` | `publish_artifact_unavailable_after_consume` | Canonical artifact resolution failed after consume. |
| `500` | `publish_attempt_state_unknown` | Consume or durable state cannot be safely proven. |
| `502` | `publish_connector_failed` | Connector explicitly returned `success=false`. |
| `502` | `publish_connector_not_ready_after_consume` | Credentials became unavailable after acceptance consume and before any outbound connector call. |
| `502` | `publish_connector_simulated` | A connector returned `simulated=true`; the attempt fails closed and never becomes published. |
| `502` | `publish_preflight_unavailable` | Read-only preflight outcome is uncertain; acceptance remains unconsumed. |
| `502` | `publish_outcome_ambiguous` | Timeout, exception, or indeterminate connector result. |

`acceptance_consumed` is `true|false|null`; `null` is unknown and always has
`retry_allowed=false`. There is no automatic retry, no acceptance restore, and
no public consume endpoint. See
[Publish acceptance consumption](../runbooks/publish-acceptance-consumption.md)
for recovery and rollback.

---

### GET /distribution/publish-attempts/{attempt_id}

Read one safe durable publish-attempt projection. The authenticated key must
carry `artifact:publish` or `all`. Lookup is bound to the authenticated tenant;
a missing or cross-tenant attempt returns the same 404.

**Headers:** `X-API-Key`

**Response:**
```json
{
  "publish_attempt_id": "91ec3593-cc3c-42bf-99ee-c98655c5826b",
  "acceptance_id": "3f4b5088-4138-47c6-96ae-c918b8297010",
  "platform": "tiktok",
  "status": "published",
  "error_code": null,
  "post_id": "1234567890123456789",
  "post_url": "https://www.tiktok.com/@brand/video/1234567890123456789",
  "receipt": {
    "schema_version": "publish-receipt.v1",
    "platform": "tiktok",
    "protocol_version": "tiktok-content-posting-v2",
    "completion_scope": "tiktok_direct_post",
    "provider_operation_id": "v_pub_file_20260714_01",
    "provider_resource_id": "1234567890123456789",
    "target_id": null,
    "provider_status": "PUBLISH_COMPLETE",
    "post_id": "1234567890123456789",
    "post_url": "https://www.tiktok.com/@brand/video/1234567890123456789",
    "public_visibility_verified": true,
    "observed_at": "2026-07-14T08:00:00Z",
    "verified_by": "video_query",
    "simulated": false
  },
  "acceptance_consumed": true,
  "retry_allowed": false,
  "created_at": "2026-07-14T07:59:58Z",
  "updated_at": "2026-07-14T08:00:00Z"
}
```

The route does not return metadata, artifact paths, raw attempt content, signed
upload/staged URLs, provider payloads, or credentials. It performs no external
call and no write. Historical `published` rows may return `receipt: null` as
legacy/unverified; they cannot authorize durable status lookup.

| HTTP | Stable code | Meaning |
|---:|---|---|
| `404` | `publish_attempt_not_found` | Attempt is absent or belongs to another tenant. |
| `503` | `publish_attempt_store_unavailable` | Durable state cannot be safely decoded or read. |

---

### GET /distribution/status/{platform}/{post_id} (deprecated)

Read an exact persisted TikTok receipt for the authenticated tenant. The key
must carry `artifact:publish` or `all`. This compatibility route performs no
connector call, external status refresh, or database write.

**Headers:** `X-API-Key`

**Path parameters:**
- `platform` -- Only `"tiktok"` remains readable; `"shopify"` is retired.
- `post_id` -- Positive-decimal public TikTok post ID from a durable receipt.

**Trusted response:**
```json
{
  "platform": "tiktok",
  "post_id": "1234567890123456789",
  "status": "PUBLISH_COMPLETE",
  "post_url": "https://www.tiktok.com/@brand/video/1234567890123456789",
  "simulated": false,
  "observed_at": "2026-07-14T08:00:00Z",
  "verified_by": "video_query"
}
```

Only an exact valid `publish-receipt.v1` on a trusted published attempt can
produce 200. The route never passes public post ID as a TikTok publish
operation ID and never selects one contradictory duplicate as “latest.”

| HTTP | Stable code | Meaning |
|---:|---|---|
| `200` | none | Trusted durable TikTok terminal receipt with `simulated=false`. |
| `400` | `distribution_status_platform_unsupported` | Platform is neither TikTok nor the retired Shopify branch. |
| `404` | `distribution_status_not_found` | No exact trusted TikTok receipt exists for this tenant/post ID. |
| `410` | `distribution_status_route_deprecated` | Shopify status compatibility is retired. |
| `503` | `publish_attempt_store_unavailable` | Receipt data is malformed, unavailable, or contradictory. |

Status lookup has no mock fallback, external refresh, or automatic retry. See
[Publish receipt protocol calibration](../runbooks/publish-receipt-protocol-calibration.md)
for incident handling and rollback boundaries.

---

## 8. Telemetry

### GET /telemetry/metrics

Return a summary of pipeline metrics.

**Headers:** `X-API-Key`

**Response:** `PipelineMetrics` summary dict (structure depends on telemetry implementation).

---

### GET /telemetry/errors

Return ErrorCollector errors, optionally filtered by pipeline label.

**Headers:** `X-API-Key`

**Query parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `label` | string (optional) | Filter errors by pipeline run label |

**Response:**
```json
{
  "errors": [...],
  "count": 0,
  "label_filter": null
}
```

---

## 9. File Upload & Media

### POST /api/upload

Upload an asset file (video, image, audio, document) to the uploads directory. Uses a sanitized UUID-based filename. Max file size: 100 MB.

**Headers:** `X-API-Key`, `Content-Type: multipart/form-data`

**Request (multipart/form-data):**
| Field | Type | Description |
|-------|------|-------------|
| `file` | file (binary) | File to upload |

Allowed extensions: `.mp4`, `.mov`, `.webm`, `.png`, `.jpg`, `.jpeg`, `.webp`, `.mp3`, `.wav`, `.m4a`, `.pdf`, `.txt`, `.md`.

**Response:**
```json
{
  "filename": "a1b2c3d4e5f6.mp4",
  "original_name": "product_demo.mp4",
  "path": "/api/media/a1b2c3d4e5f6.mp4",
  "size": 5242880,
  "content_type": "video/mp4"
}
```

Returns `413` if the file exceeds 100 MB. Returns `400` if the file type is not allowed.

---

## 10. Canonical Async Submission & Recovery

Fast Mode and S1-S5 use a durable, tenant-scoped idempotency ledger on their
canonical asynchronous submit paths. This contract prevents a lost or delayed
HTTP response from creating a second paid job.

The following endpoints require both headers:

```http
X-API-Key: <tenant-api-key>
Idempotency-Key: <opaque-action-key>
```

`Idempotency-Key` is not an authentication credential. It must contain 16-128
characters and match `^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$`. It is
case-sensitive, must occur exactly once, and must not be placed in the request
body or URL. The server stores only its SHA-256 digest; the raw value is never
returned or logged by this API.

One explicit Start/Generate action must use one stable key. Do not generate a
new key merely because a response timed out or the browser reloaded.

### POST /fast/submit

Submit Fast Mode generation and return the durable job identity without
waiting for generation to finish.

**Headers:** `X-API-Key`, `Idempotency-Key`

**Request body:** The validated Fast Mode request used by `/fast/generate`, for
example:

```json
{
  "user_prompt": "Create a 15-second vertical product introduction",
  "duration": 15,
  "enable_tts": false
}
```

**First accepted response:**

```json
{
  "task_id": "fast_1783830000_a1b2c3d4",
  "status": "queued",
  "started_at_unix": 1783830000,
  "idempotent_replay": false
}
```

An exact same-tenant replay returns the original `task_id` and current stored
submit status with `idempotent_replay: true`. Poll the original resource with
`GET /fast/status/{task_id}` only after the response/readback status is
`queued`, `running`, or terminal.

### POST /scenario/{scenario}/submit

Submit S1-S5 (`scenario` is `s1`, `s2`, `s3`, `s4`, or `s5`) for background
execution. The request body is the validated scenario-specific body used by
the corresponding blocking endpoint.

**Headers:** `X-API-Key`, `Idempotency-Key`

**First accepted response:**

```json
{
  "label": "s1_1783830000_a1b2c3d4",
  "status": "queued",
  "trace_id": "a1b2c3d4",
  "idempotent_replay": false
}
```

An exact same-tenant replay returns the original `label` and current stored
submit status with `idempotent_replay: true`. Poll the original resource with
`GET /scenario/{scenario}/status/{label}` only after the response/readback
status is `queued`, `running`, or terminal. A replay observed while the owner
is still preparing the job may truthfully return `reserved` or `initializing`;
continue idempotency readback instead of posting again.

### GET /submissions/idempotency

Read the original submission by sending its `Idempotency-Key` header. This is
an authenticated tenant read and does not perform a second provider-submit
authorization or generation mutation.

**Headers:** `X-API-Key`, `Idempotency-Key`

**Response:**

```json
{
  "resource_type": "scenario",
  "resource_id": "s1_1783830000_a1b2c3d4",
  "scenario": "s1",
  "status": "running",
  "submit_response": {
    "label": "s1_1783830000_a1b2c3d4",
    "status": "running",
    "trace_id": "a1b2c3d4",
    "idempotent_replay": false
  },
  "stage": "running",
  "effective_policy_version": "generation-safety.v1",
  "created_at": "2026-07-12T00:00:00Z",
  "updated_at": "2026-07-12T00:00:04Z"
}
```

Terminal readback may additionally include an allowlisted `result_snapshot`
and `safe_error_code`. It never returns the raw idempotency key, request body,
authentication material, provider credentials, or raw exception text.

Unknown keys and keys owned by another tenant both return the same `404`
`submission_not_found` response. If the browser account/API key changed while
a submission was pending, restore the original tenant context and read again;
do not infer that the original job never existed.

### Replay, conflict, and tenant rules

- Same tenant + same key + same canonical business request returns the original
  resource. It never creates a second execution owner.
- Reusing the key in the same tenant with a changed payload, effective policy,
  operation, or scenario returns `409 idempotency_payload_conflict` without
  translation, state initialization, task creation, or provider work.
- The key namespace is tenant-global: using one key for Fast and S1 in the same
  tenant conflicts. Different tenants may independently use the same opaque
  raw value and cannot read each other's record.
- Request-scoped provider credentials are excluded from the fingerprint and
  are not persisted for replay. A definitively failed job remains the original
  job; a corrected attempt is a new explicit action with a new key.
- Records do not automatically expire or reopen a used key.

### Error contract and ambiguous responses

Errors use `{"detail":{"code":"..."}}` (plus the normal response `_meta`
wrapper where applicable):

| HTTP | Code | Meaning / caller action |
|---|---|---|
| `400` | `idempotency_key_required` | Required header is missing. Upgrade the caller before submitting. |
| `400` | `idempotency_key_invalid` | Header is duplicated or does not match the length/format contract. |
| `409` | `idempotency_payload_conflict` | The tenant/key already belongs to a different canonical request. Do not auto-generate a replacement key. |
| `404` | `submission_not_found` | Readback key is unknown in this tenant, including cross-tenant lookup. |
| `422` | Sanitized validation detail (`type` / `loc` / `msg`) | A body field such as unsupported `idempotency_key`, scenario payload, or type is invalid. Request input, provider credentials, and validation context are never echoed. |
| `503` | `idempotency_store_unavailable` | Durable authority was unavailable before claim/downstream work. Definitive pre-claim failure; never auto-retry a mutation. |
| `503` | `submission_state_uncertain` | A claim may exist but a later durable transition was uncertain. Treat as ambiguous and use GET readback with the same key. |
| `500` | `submission_initialization_failed` | Initialization could not complete. Treat a dispatched response as ambiguous until same-key readback resolves it. |

Network failure, client timeout/abort after dispatch, unstructured proxy
`500`/`502`/`503`/`504`, and `submission_state_uncertain` are ambiguous. The
caller must keep the original pending key and use bounded
`GET /submissions/idempotency` readback. It must not send a blind second POST.

`recovery_required` preserves the original resource identity but means the
nonterminal owner was lost and this release will not automatically resume paid
work. Render that state directly, keep it separate from `404`, and require an
explicit abandon/new-action decision before creating another key.

Blocking and legacy mutations such as `/fast/generate`, `/scenario/s1` through
`/scenario/s5`, `/scenario/s1/start`, `/pipeline/start`, gate, regenerate,
publish, and delivery endpoints are outside this replay contract and remain
non-replayable in this batch.

See [Submission idempotency recovery](../runbooks/submission-idempotency-recovery.md)
for browser recovery and migration/operations sequencing.

---

## 11. Artifact Acceptance Records

W1-22 records a reviewer decision against the exact bytes of a canonical async
Fast or S1-S5 final video. All three routes require `X-API-Key` with
`artifact:accept` or `all`; a key with only `provider:submit` receives
`403 Insufficient permission`.

An accepted source must be a tenant-owned durable submission with an exact
canonical `pending_review` final-video path. For an accepted decision it must
also be `completed`, `full_media_success=true`, non-stub, and non-degraded. A
rejected decision still requires a terminal source with a valid final-video
projection. Tenant, reviewer, scenario, digest, size, status, expiry, and
consume metadata are server-owned.

### POST /acceptance-records

Create one accepted/rejected decision. This route additionally requires one
action-stable `Idempotency-Key` header (16-128 characters using the canonical
opaque-key grammar).

**Request:**

```json
{
  "source_resource_type": "scenario",
  "source_resource_id": "s1_1783830000_a1b2c3d4",
  "artifact_path": "tenants/tenant-a/pending_review/s1_1783830000_a1b2c3d4/assemble/final.mp4",
  "decision": "accepted",
  "review_notes": "Final video reviewed against the approved brief.",
  "expires_in_seconds": 3600
}
```

**Owner response:** `201`

**Idempotent replay response:** `200`, returns the original record with
`idempotent_replay: true`. Same tenant/key with a different fingerprint returns
`409 acceptance_payload_conflict` and does not change the original decision.

**Response shape:**

```json
{
  "acceptance_id": "3f4b5088-4138-47c6-96ae-c918b8297010",
  "tenant_id": "tenant-a",
  "source_resource_type": "scenario",
  "source_resource_id": "s1_1783830000_a1b2c3d4",
  "scenario": "s1",
  "artifact": {
    "path": "tenants/tenant-a/pending_review/s1_1783830000_a1b2c3d4/assemble/final.mp4",
    "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "size_bytes": 123456,
    "kind": "video"
  },
  "decision": "accepted",
  "status": "available",
  "reviewer": {"key_id": "reviewer-key-id", "key_type": "tenant"},
  "review_notes": "Final video reviewed against the approved brief.",
  "expires_at": "2026-07-12T12:00:00Z",
  "consumed_at": null,
  "revoked_at": null,
  "idempotent_replay": false,
  "created_at": "2026-07-12T11:00:00Z",
  "updated_at": "2026-07-12T11:00:00Z"
}
```

Creating a rejection transactionally revokes an older available record for the
same tenant and artifact path before inserting the rejected record. The
rejection itself is never consumable.

### GET /acceptance-records/{acceptance_id}

Tenant-bound read. Success is `200`. Unknown and cross-tenant IDs both return
`404 acceptance_not_found`. Read reconciles expiry using database time; a
reconciled record is returned with `status: "expired"` and is not reopened.

### POST /acceptance-records/{acceptance_id}/revoke

Revoke one available record. Success is `200`; replaying revoke on an already
revoked record returns the same revoked record and original timestamp with
`200`. Consumed, expired, or rejected records return
`409 acceptance_not_revocable`.

### Safe error contract

| HTTP | Code / shape | Meaning |
|---:|---|---|
| `400` | `acceptance_key_required` | Create is missing the action-stable key. |
| `400` | `acceptance_key_invalid` | The key is duplicated or fails length/format validation. |
| `403` | `Insufficient permission` | `artifact:accept|all` is absent; `provider:submit` alone is insufficient. |
| `404` | `acceptance_not_found` | Source, record, or artifact is not visible in the authenticated tenant. |
| `409` | `acceptance_payload_conflict` | Same create key has a different fingerprint. |
| `409` | `acceptance_source_not_terminal` | Durable source is still running. |
| `409` | `acceptance_source_not_eligible` | Source is not an eligible final-video projection. |
| `409` | `acceptance_artifact_mismatch` | Requested path is not the durable exact final path. |
| `409` | `acceptance_already_available` | Another available record owns the tenant/path. |
| `409` | `acceptance_not_revocable` | Current state cannot be revoked. |
| `409` | `acceptance_not_available` | Internal single-use consume found a non-available record. |
| `409` | `acceptance_expired` | Internal consume reconciled DB-time expiry. |
| `409` | `acceptance_artifact_integrity_mismatch` | Internal consume found changed/missing bytes. |
| `422` | sanitized `type` / `loc` / `msg` | Invalid JSON/body; input, context, URL, credentials, and raw exceptions are not echoed. |
| `503` | `acceptance_store_unavailable` | Durable ledger is unavailable; there is no memory/filesystem fallback. |

### Consume and release boundary

There is **no HTTP consume** endpoint and **no UI** added by W1-22. The
`consume_for_publish(...)` service call is internal and single-use: it checks
database-time expiry, re-hashes the exact file, verifies path/digest/size
integrity, and atomically lets only one consumer change `available` to
`consumed`. Read `200` does not perform this integrity check and is not publish
authority.

W1-23 now consumes this internal authority through the authenticated canonical
and deprecated publish adapters. The acceptance row records
`consumed_by_operation=distribution.publish` and
`consumed_by_resource_id=<publish_attempt_id>` for correlation. If consume-store
truth is uncertain, one internal read-only inspection returns only
available/this-attempt/other-attempt/not-available/unknown truth; it does not
consume again, restore authority, or call a connector. There remains no HTTP
consume endpoint and no W1-23 review UI.

Current evidence is `W1-23 completed_local` only: `production unchanged`,
`provider_call=false`, `live_publish=false`. It does not claim production
migration, live acceptance, publish, delivery, or immutable artifact snapshot.

See [Artifact acceptance lifecycle](../runbooks/artifact-acceptance-lifecycle.md)
for operator recovery, expiry, integrity, rejection, and the ordered recovery
table contract (including the provider-cost ledger tables).
See [Publish acceptance consumption](../runbooks/publish-acceptance-consumption.md)
for no-automatic-retry/no-restore rules and attempt correlation.

---

## Summary of Endpoints

| # | Method | Path | Section |
|---|--------|------|---------|
| 1 | GET | `/health` | Health & Diagnostics |
| 2 | POST | `/scenario/s1` | S1 Product Direct |
| 3 | POST | `/scenario/s1/start` | S1 Product Direct |
| 4 | POST | `/scenario/s1/step/{step_name}` | S1 Product Direct |
| 5 | POST | `/scenario/s1/regenerate` | S1 Product Direct |
| 6 | POST | `/scenario/s1/resume` | S1 Product Direct |
| 7 | GET | `/scenario/s1/state/{label}` | S1 Product Direct |
| 8 | PUT | `/scenario/s1/state/{label}` | S1 Product Direct |
| 9 | GET | `/scenario/{scenario}/state/{label}/steps` | Generic Pipeline |
| 10 | POST | `/scenario/{scenario}/step/{step_name}` | Generic Pipeline |
| 11 | PUT | `/scenario/{scenario}/state/{label}` | Generic Pipeline |
| 12 | POST | `/scenario/{scenario}/regenerate/{label}/{step_name}` | Generic Pipeline |
| 13 | POST | `/scenario/s2` | S2 / S3 / S4 |
| 14 | POST | `/scenario/s3` | S2 / S3 / S4 |
| 15 | POST | `/scenario/s4` | S2 / S3 / S4 |
| 16 | POST | `/pipeline/start` | Legacy Pipeline |
| 17 | GET | `/pipeline/{thread_id}/state` | Legacy Pipeline |
| 18 | POST | `/pipeline/{thread_id}/review/{review_node}` | Legacy Pipeline |
| 19 | GET | `/pipeline/{thread_id}/distribution` | Legacy Pipeline |
| 20 | GET | `/pipeline/{thread_id}/output` | Legacy Pipeline |
| 21 | GET | `/pipeline/{thread_id}/export` | Legacy Pipeline |
| 22 | GET | `/api/files` | Assets |
| 23 | GET | `/api/media/{filename}` | Assets |
| 24 | POST | `/api/assets/upload` | Assets |
| 25 | GET | `/api/assets/` | Assets |
| 26 | GET | `/api/assets/{asset_id}` | Assets |
| 27 | DELETE | `/api/assets/{asset_id}` | Assets |
| 28 | PUT | `/api/assets/{asset_id}/tags` | Assets |
| 29 | GET | `/api/assets/brand-packages` | Assets |
| 30 | POST | `/api/assets/brand-packages` | Assets |
| 31 | GET | `/api/assets/brand-packages/{package_id}` | Assets |
| 32 | DELETE | `/api/assets/brand-packages/{package_id}` | Assets |
| 33 | GET | `/api/assets/influencers` | Assets |
| 34 | POST | `/api/assets/influencers` | Assets |
| 35 | GET | `/api/assets/influencers/{influencer_id}` | Assets |
| 36 | PUT | `/api/assets/influencers/{influencer_id}/product-links` | Assets |
| 37 | DELETE | `/api/assets/influencers/{influencer_id}` | Assets |
| 38 | POST | `/api/assets/remix-brief` | Assets |
| 39 | GET | `/distribution/platforms` | Distribution |
| 40 | POST | `/distribution/publish` | Distribution |
| 41 | POST | `/publish/{video_id}` | Distribution (deprecated adapter) |
| 42 | GET | `/distribution/publish-attempts/{attempt_id}` | Distribution |
| 43 | GET | `/distribution/status/{platform}/{post_id}` | Distribution (deprecated durable readback) |
| 44 | GET | `/telemetry/metrics` | Telemetry |
| 45 | GET | `/telemetry/errors` | Telemetry |
| 46 | POST | `/api/upload` | File Upload & Media |
| 47 | POST | `/fast/submit` | Canonical Async Submission & Recovery |
| 48 | POST | `/scenario/{scenario}/submit` | Canonical Async Submission & Recovery |
| 49 | GET | `/submissions/idempotency` | Canonical Async Submission & Recovery |
| 50 | POST | `/acceptance-records` | Artifact Acceptance Records |
| 51 | GET | `/acceptance-records/{acceptance_id}` | Artifact Acceptance Records |
| 52 | POST | `/acceptance-records/{acceptance_id}/revoke` | Artifact Acceptance Records |

**Documented here: 52 endpoints**
