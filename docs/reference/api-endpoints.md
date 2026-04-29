# API Endpoint Reference

**Service:** Short Video Agent API (FastAPI)  
**Base URL:** `http://localhost:8001`  
**Version:** `0.2.0`  

## Authentication

All endpoints **except** `GET /health` require the `X-API-Key` header.

```
X-API-Key: <your-api-key>
```

If the `API_KEY` environment variable is not set, the server generates a temporary key on startup and logs it to the console.

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
- `scenario` -- Currently only `"s1"`.
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

### POST /pipeline/start

Start a new legacy pipeline run. Returns a `thread_id` for tracking. Translates Chinese product inputs to English. Runs until the first human-review interrupt.

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
  "content_scenario": "influencer_remix",
  "api_keys": {
    "openai": "sk-...",
    "elevenlabs": "..."
  }
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `api_keys` | object | `{}` | Optional API keys injected into env for this process |

**Response:**
```json
{
  "thread_id": "a1b2c3d4",
  "status": "interrupted",
  "events": [{"event1": "..."}]
}
```

**Key fields:**
- `thread_id` -- Unique 8-char hex identifier for this pipeline run.
- `status` -- `"interrupted"` (waiting for human review) or `"complete"`.

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
- `current_review` -- The review node name if pipeline is interrupted (`"strategy_review"`, `"script_review"`, `"edit_review"`, `"thumbnail_review"`), or `null`.
- `state` -- Full pipeline state dict.

---

### POST /pipeline/{thread_id}/review/{review_node}

Submit a human review decision for a pipeline checkpoint and resume execution. Includes double-click guard (idempotent) -- if the review was already processed, returns `"idempotent_skip"`.

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

**Response (approved):**
```json
{
  "thread_id": "a1b2c3d4",
  "review_node": "strategy_review",
  "action": "approve",
  "status": "resumed",
  "events": [{"step": "scripting", "result": {...}}]
}
```

**Response (rejected):** Pipeline terminates.
```json
{
  "thread_id": "a1b2c3d4",
  "review_node": "strategy_review",
  "action": "reject",
  "status": "rejected",
  "events": []
}
```

**Response (double-click guard):**
```json
{
  "thread_id": "a1b2c3d4",
  "review_node": "strategy_review",
  "action": "approve",
  "status": "idempotent_skip",
  "message": "Review already processed",
  "events": []
}
```

**Key fields:**
- `status` -- `"resumed"` (execution continues), `"rejected"` (pipeline terminated), or `"idempotent_skip"` (no-op).
- If the reviewed node is `thumbnail_review` and action is `"approve"`, the pipeline is marked complete.

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

Returns `404` if thread not found.

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

Publish content to a platform (TikTok or Shopify).

**Headers:** `X-API-Key`

**Request body:**
```json
{
  "platform": "tiktok",
  "content": {
    "video_path": "/output/renders/final.mp4",
    "caption": "Check out our new ergonomic chair! #officegoals",
    "hashtags": ["ergonomic", "office", "comfort"]
  }
}
```

**Response:**
```json
{
  "success": true,
  "post_id": "tiktok_post_123456",
  "url": "https://tiktok.com/@brand/video/123456",
  "error": null
}
```

**Key fields:**
- `post_id` -- Platform-specific post identifier.
- `url` -- Public URL to the published post.
- The publish is logged to `PublishLogRepository` when PostgreSQL is available.

---

### GET /distribution/status/{platform}/{post_id}

Get the publish status for a post on a platform.

**Headers:** `X-API-Key`

**Path parameters:**
- `platform` -- `"tiktok"` or `"shopify"`.
- `post_id` -- Post identifier returned from the publish endpoint.

**Response:**
```json
{
  "post_id": "tiktok_post_123456",
  "status": "published",
  "views": 1500,
  "url": "https://tiktok.com/@brand/video/123456"
}
```

The response structure varies by platform connector implementation.

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
| 41 | GET | `/distribution/status/{platform}/{post_id}` | Distribution |
| 42 | GET | `/telemetry/metrics` | Telemetry |
| 43 | GET | `/telemetry/errors` | Telemetry |
| 44 | POST | `/api/upload` | File Upload & Media |

**Total: 44 endpoints**
