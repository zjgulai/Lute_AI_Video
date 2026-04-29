# Layer 5: Commercial Distribution Loop -- Implementation Plan

> Status: Approved for implementation | Version: v1.0 | Date: 2026-04-30
> Design Spec: `2026-04-30-layer5-distribution-design.md`

---

## Implementation Strategy

Four parallel tracks, all targeting the same commit. Track 4 (Integration + Verification) is the gate: it can only be verified once Tracks 1-3 are complete.

### Dependency Graph

```
Track 1 (DB + Metrics) ------+
                              +--> Track 4 (Integration + Verification)
Track 2 (Publish Engine) -----+
                              |
Track 3 (Frontend Dashboard) -+
```

**No dependencies between Tracks 1-3** -- they can be implemented in any order.
Track 4 depends on all three.

---

## Track 1: Database + Metrics Poller (Backend)

### Files to Create

#### 1.1 `src/storage/metrics_repository.py` -- New Video Metrics Repository

**Purpose**: CRUD for the `video_metrics` table. This is a NEW file (the existing `src/tools/metrics_repository.py` is for pipeline run metrics, *not* video metrics -- they should remain separate).

**Key Functions:**

```python
class VideoMetricsRepository:
    """CRUD for video_metrics table. Dual-write: PG (when healthy) + SQLite fallback."""

    async def save_metrics(
        self, video_id: str, scenario: str, platform: str,
        post_id: str, post_url: str, metrics: dict,
        published_at: str | None = None
    ) -> dict:
        """Insert a new metrics snapshot row. Returns the created record."""

    async def get_metrics(
        self, video_id: str, platform: str | None = None,
        limit: int = 50
    ) -> list[dict]:
        """Get all metrics snapshots for a video, newest first.
        When platform is None, returns all platforms."""

    async def get_active_posts(
        self, max_age_days: int = 30
    ) -> list[dict]:
        """Get distinct (video_id, platform) pairs that have been published
        and are still within the polling window. Excludes posts older than
        max_age_days. Returns list of dicts with video_id, scenario, platform,
        post_id, post_url, latest_published_at."""

    async def get_dashboard_overview(
        self, scenario: str | None = None,
        platform: str | None = None,
        hours: int | None = 168
    ) -> dict:
        """Aggregate metrics across all videos for dashboard display.
        Returns:
            - totals: count of published videos, platforms, metrics snapshots
            - by_scenario: S1/S2/S3 aggregation with avg watch_rate, ctr, cvr
            - by_platform: tiktok/shopify comparison with per-platform averages
            - top_videos: top 10 videos by watch_rate"""

    async def get_latest_metrics(
        self, video_id: str, platform: str
    ) -> dict | None:
        """Get the single most recent metrics snapshot for a video+platform."""

    async def get_videos_for_platform(
        self, platform: str, scenario: str | None = None,
        limit: int = 100
    ) -> list[dict]:
        """Get distinct published videos for a specific platform, with their
        latest metrics snapshot."""

    async def save_publish_record(
        self, video_id: str, scenario: str, platform: str,
        post_id: str, post_url: str, published_at: str
    ) -> dict:
        """Save a publish event record (first metrics snapshot)."""
```

**Implementation Notes:**
- Follow the exact dual-write pattern from `src/storage/repository.py` (`BaseRepository._fetchrow`, `_fetch`, `_execute`)
- Use `get_pool()` and `get_sqlite_conn()` from `src/storage/db.py`
- For the `get_dashboard_overview` aggregation, use SQL GROUP BY queries on the SQLite side (available as stdlib)
- Do NOT use `BaseRepository` directly because `video_metrics` is not one of the allowed tables in `_ALLOWED_FIELDS` -- write raw SQL through the dual-write helpers
- The `metrics` dict should be stored as JSON text (SQLite has no JSONB, but `json_extract` works on text columns)

#### 1.2 `src/tasks/__init__.py` -- Package init (create if not exists)

```python
# Tasks package for background jobs
```

#### 1.3 `src/tasks/metrics_poller.py` -- New Metrics Poller

**Purpose**: Background task that periodically fetches metrics from TikTok and Shopify APIs.

**Key Functions:**

```python
class MetricsPoller:
    """Background metrics poller with time-based polling strategy."""

    def __init__(self):
        self.repo = VideoMetricsRepository()
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self, interval_minutes: int = 120):
        """Start the polling loop. Runs until stop() is called."""
        self._running = True
        while self._running:
            await self.pull_all()
            await asyncio.sleep(interval_minutes * 60)

    async def stop(self):
        """Gracefully stop the polling loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None

    async def pull_all(self):
        """Iterate all active posts and pull fresh metrics for each.
        Implements the per-post time-based strategy:
        - 0-24h since published: poll every 2h (default interval)
        - 24-72h: poll every 6h
        - 3d-30d: poll every 12h
        - 30d+: skip (post expired)"""

    async def pull_single(self, post: dict) -> dict | None:
        """Fetch the latest metrics for a single post and store them.
        Returns the saved metrics dict or None on failure."""

    async def _fetch_from_tiktok(self, post_id: str) -> dict:
        """Call TikTok Business API Insights endpoint.
        Mock fallback when TIKTOK_ACCESS_TOKEN is empty:
        returns {'watch_rate': 0.72, 'ctr': 0.042, 'followers_gained': 15,
                 'likes': 124, 'comments': 8, 'shares': 22, 'views': 4520}"""

    async def _fetch_from_shopify(self, post_id: str) -> dict:
        """Call Shopify Admin API Analytics endpoint.
        Mock fallback when SHOPIFY_ACCESS_TOKEN is empty:
        returns {'cvr': 0.028, 'sales': 3, 'views': 1520}"""

    def _should_poll(self, published_at: str) -> bool:
        """Determine if a post should be polled based on its age.
        Returns False for posts older than 30 days."""

    def _get_interval_for_age(self, age_hours: float) -> int:
        """Return the polling interval in hours based on post age."""
        if age_hours <= 24:
            return 2
        elif age_hours <= 72:
            return 6
        elif age_hours <= 30 * 24:
            return 12
        return 0  # Stop polling
```

**Time-based polling strategy (self-verification table):**

| Age Range | Interval | Still Active? |
|-----------|----------|---------------|
| 0-24h     | 2h       | Yes |
| 24-72h    | 6h       | Yes |
| 3d-30d    | 12h      | Yes |
| 30d+      | N/A      | No (archived) |

**Mock fallback:** When `TIKTOK_ACCESS_TOKEN` or `SHOPIFY_ACCESS_TOKEN` is empty/absent, `_fetch_from_tiktok` and `_fetch_from_shopify` return deterministic mock data. This ensures the MetricsPoller is always functional during development.

### Files to Modify

#### 1.4 `src/storage/db.py` -- Add `video_metrics` table to SQLite schema

**Modification**: In the `_create_sqlite_tables()` function, add a new `CREATE TABLE` statement after the existing `publish_logs` table:

```python
# Add inside _create_sqlite_tables():
CREATE TABLE IF NOT EXISTS video_metrics (
    id TEXT PRIMARY KEY,
    video_id TEXT NOT NULL,
    scenario TEXT NOT NULL,
    platform TEXT NOT NULL,
    post_id TEXT,
    post_url TEXT,
    metrics TEXT NOT NULL DEFAULT '{}',
    pulled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_vm_video_id ON video_metrics(video_id);
CREATE INDEX IF NOT EXISTS idx_vm_scenario ON video_metrics(scenario);
CREATE INDEX IF NOT EXISTS idx_vm_platform ON video_metrics(platform);
CREATE INDEX IF NOT EXISTS idx_vm_pulled_at ON video_metrics(pulled_at);
```

Also update `_REQUIRED_TABLES` list to include `"video_metrics"`.

### Self-Verification for Track 1

1. Run `python -c "from src.storage.db import _create_sqlite_tables; print('tables OK')"` -- no import errors
2. Run `python -c "from src.storage.metrics_repository import VideoMetricsRepository; print('repo OK')"` -- no import errors
3. Run `python -c "from src.tasks.metrics_poller import MetricsPoller; m = MetricsPoller(); print('poller OK')"` -- no import errors
4. Write a short verification script that:
   - Initializes an in-memory SQLite database
   - Creates VideoMetricsRepository
   - Calls `save_metrics()` and `get_metrics()` and checks the returned data
   - Calls `get_active_posts()` and verifies correct filtering
   - Calls `get_dashboard_overview()` and checks aggregation fields exist
5. Verify all indexes were created: `python -c "import sqlite3; c=sqlite3.connect(':memory:'); c.executescript(open('src/storage/db.py').read()); [print(r) for r in c.execute('SELECT name FROM sqlite_master WHERE type=\"index\"').fetchall()]"`

---

## Track 2: Publish Engine (Backend)

### Files to Create

#### 2.1 `src/connectors/publish_engine.py` -- New Publish Engine

**Purpose**: Unified publish orchestrator that calls platform-specific connectors and stores publish records.

**Key Functions:**

```python
@dataclass
class PublishResult:
    success: bool
    platform: str
    post_id: str | None = None
    post_url: str | None = None
    error: str | None = None
    published_at: str | None = None


class PublishEngine:
    """Unified publish orchestrator."""

    def __init__(self):
        self.metrics_repo = VideoMetricsRepository()

    async def publish(
        self, video_path: str, metadata: dict,
        platforms: list[str]
    ) -> list[PublishResult]:
        """Publish a single video to multiple platforms.
        Returns a list of PublishResult, one per platform.
        Stores publish records in video_metrics table."""

    async def publish_to_tiktok(
        self, video_path: str, metadata: dict
    ) -> PublishResult:
        """Publish to TikTok via Content Posting API.
        Mock fallback when TIKTOK_ACCESS_TOKEN is missing:
        returns PublishResult(success=True, post_id='tt_mock_...',
                post_url='https://tiktok.com/@mock/video/...')"""

    async def publish_to_shopify(
        self, video_path: str, metadata: dict
    ) -> PublishResult:
        """Publish to Shopify via Admin API (Files + Product Media).
        Mock fallback when SHOPIFY_ACCESS_TOKEN is missing:
        returns PublishResult(success=True, post_id='sp_mock_...',
                post_url='https://mock-store.myshopify.com/...')"""
```

**TikTok Publish Flow:**
1. Check `TIKTOK_ACCESS_TOKEN` from `src.config` -- if empty, return mock result
2. Call TikTok Content Posting API: `POST https://open-api.tiktok.com/video/publish/`
3. Upload video file as multipart upload
4. Set title from `metadata.get('hook_text', '')` or `metadata.get('title', '')`
5. Set hashtags from `metadata.get('hashtags', [])`
6. Return post_id and post_url from API response

**Shopify Publish Flow:**
1. Check `SHOPIFY_ACCESS_TOKEN` from `src.config` -- if empty, return mock result
2. Upload video to Shopify Files API: `POST /admin/api/2024-04/graphql.json` with `fileCreate` mutation
3. Get file ID from response
4. Associate video with product: search product by name from metadata, then `productMediaCreate` mutation
5. Return product_media_id and admin_url

**Metadata contract:**
```python
{
    "video_id": str,          # pipeline video identifier
    "scenario": str,          # S1/S2/S3
    "hook_text": str,         # extracted hook for title
    "hashtags": list[str],    # extracted hashtags
    "product_name": str,      # for Shopify product matching
    "brand_name": str,        # optional, for branding
    "title": str,             # fallback title
    "description": str,       # video description
    "thumbnail_url": str,     # optional thumbnail
}
```

### Files to Modify

#### 2.2 `src/connectors/tiktok_connector.py` -- Replace Mock with Real API

**Modification**: Replace the mock `publish()` implementation with real TikTok Content Posting API calls. Keep the `get_status()` method updated to call real TikTok Insights API.

**Key Changes:**
- Import `TIKTOK_ACCESS_TOKEN` from `src.config`
- Add `_call_tiktok_api(endpoint, method, data, files)` helper
- `publish()`: real API with mock fallback when token missing
- `get_status()`: real Insights API with mock fallback when token missing

**API Endpoints:**
- Publish: `https://open-api.tiktok.com/video/publish/` (POST, multipart)
- Status: `https://open-api.tiktok.com/video/query/` (GET, with post_id)
- Insights: `https://open-api.tiktok.com/video/insights/` (GET, metrics query)

#### 2.3 `src/connectors/shopify_connector.py` -- Replace Mock with Real API

**Modification**: Replace the mock `publish()` with real Shopify Admin API (GraphQL) calls.

**Key Changes:**
- Import `SHOPIFY_ACCESS_TOKEN` from `src.config`
- Add `SHOPIFY_STORE_URL` to `src/config.py` (read from env)
- Add `_call_shopify_graphql(query, variables)` helper
- `publish()`: real File upload + ProductMediaCreate with mock fallback
- `get_status()`: real product media status with mock fallback

**GraphQL Operations:**
- File create: `mutation fileCreate($files: [FileInput!]!) { fileCreate(files: $files) { ... } }`
- Product media create: `mutation productMediaCreate($media: [ProductMediaInput!]!) { productMediaCreate(media: $media) { ... } }`
- Product search: `query products($query: String!) { products(first: 5, query: $query) { ... } }`

#### 2.4 `src/api.py` -- Add 4 New API Endpoints

**Modification**: Add these four endpoints to the existing FastAPI app. Place them after the existing distribution endpoints (after the `/distribution/platforms` endpoint at roughly line 1275) and before the file upload section.

**New Endpoints:**

```python
# --- Layer 5 endpoints (add after distribution endpoints) ---

@app.post("/publish/{video_id}", dependencies=[Depends(verify_api_key)])
async def publish_video(video_id: str, body: dict):
    """Publish a video to specified platforms.
    Body: { platforms: ["tiktok", "shopify"], metadata: {...} }
    Returns: list of PublishResult"""
    from src.connectors.publish_engine import PublishEngine
    engine = PublishEngine()
    metadata = body.get("metadata", {})
    metadata["video_id"] = video_id
    results = await engine.publish(
        video_path=metadata.get("video_path", ""),
        metadata=metadata,
        platforms=body.get("platforms", [])
    )
    return {"video_id": video_id, "results": [r.__dict__ for r in results]}


@app.get("/metrics/{video_id}", dependencies=[Depends(verify_api_key)])
async def get_video_metrics(
    video_id: str,
    platform: str | None = None,
    limit: int = 50
):
    """Get metrics history for a video.
    Query params: platform (optional filter), limit (default 50)
    Returns: { video_id, metrics: [...] }"""
    from src.storage.metrics_repository import VideoMetricsRepository
    repo = VideoMetricsRepository()
    repo.initialize()
    metrics = await repo.get_metrics(video_id, platform, limit)
    return {"video_id": video_id, "metrics": metrics}


@app.get("/dashboard/overview", dependencies=[Depends(verify_api_key)])
async def dashboard_overview(
    scenario: str | None = None,
    platform: str | None = None,
    hours: int = 168
):
    """Get aggregated dashboard data.
    Query params: scenario, platform, hours (default 168 = 7 days)
    Returns: dashboard overview dict"""
    from src.storage.metrics_repository import VideoMetricsRepository
    repo = VideoMetricsRepository()
    repo.initialize()
    overview = await repo.get_dashboard_overview(scenario, platform, hours)
    return overview


@app.post("/metrics/pull", dependencies=[Depends(verify_api_key)])
async def manual_metrics_pull():
    """Manually trigger a metrics pull for all active posts.
    Returns: { status: str, pulled: int }"""
    from src.tasks.metrics_poller import MetricsPoller
    poller = MetricsPoller()
    await poller.pull_all()
    return {"status": "completed", "pulled": 0}  # count TBD from pull_all return
```

#### 2.5 `src/config.py` -- Add Shopify Store URL

**Modification**: Add one new config variable:

```python
# Add after SHOPIFY_ACCESS_TOKEN:
SHOPIFY_STORE_URL = os.getenv("SHOPIFY_STORE_URL", "")
```

### Self-Verification for Track 2

1. Run `python -c "from src.connectors.publish_engine import PublishEngine; e = PublishEngine(); print('engine OK')"` -- no import errors
2. Run the publish engine with mock mode:
   ```python
   import asyncio
   from src.connectors.publish_engine import PublishEngine
   async def test():
       engine = PublishEngine()
       results = await engine.publish("dummy.mp4", {"video_id": "v1", "scenario": "S1", "title": "Test"}, ["tiktok", "shopify"])
       assert len(results) == 2
       assert all(r.success for r in results)
       print("Mock publish OK")
   asyncio.run(test())
   ```
3. Verify that existing `publish_to_platform()` in `registry.py` still works:
   ```python
   from src.connectors.registry import publish_to_platform
   import asyncio
   async def test():
       r = await publish_to_platform("tiktok", {"title": "test"})
       print(r)
   asyncio.run(test())
   ```
4. Run `python -m py_compile src/connectors/tiktok_connector.py`
5. Run `python -m py_compile src/connectors/shopify_connector.py`
6. Run `python -m py_compile src/api.py`

---

## Track 3: Performance Dashboard (Frontend)

### Files to Create

#### 3.1 `web/src/components/PerformanceDashboard.tsx` -- New Component

**Purpose**: Three-view performance dashboard showing video metrics with filtering and trend visualization.

**Structure:**

```tsx
"use client";

import { useEffect, useState, useMemo } from "react";
import { useI18n } from "@/i18n/I18nProvider";

interface MetricsSnapshot {
  id: string;
  video_id: string;
  scenario: string;
  platform: string;
  post_id: string | null;
  post_url: string | null;
  metrics: Record<string, number>;
  pulled_at: string;
  published_at: string | null;
}

interface DashboardOverview {
  totals: { videos: number; platforms: number; snapshots: number };
  by_scenario: Array<{
    scenario: string; avg_watch_rate: number; avg_ctr: number;
    avg_cvr: number; video_count: number;
  }>;
  by_platform: Array<{
    platform: string; avg_watch_rate: number; avg_ctr: number;
    avg_cvr: number; avg_followers_gained: number; avg_sales: number;
    video_count: number;
  }>;
  top_videos: Array<{ video_id: string; watch_rate: number; ctr: number; cvr: number; scenario: string; platform: string }>;
}

type DashboardView = "videos" | "scenarios" | "platforms";
```

**View 1: Video Effect List (default "videos" tab)**
- Table/list of all published videos with columns: Video ID, Scenario, Platform, Watch Rate, CTR, CVR, Followers Gained, Sales, Last Pulled
- Filter bar: scenario dropdown (All/S1/S2/S3), platform dropdown (All/TikTok/Shopify), time range (24h/7d/30d/All)
- CTR > 4% green highlight, CTR < 2% red warning
- Each row expandable to show trend line chart (use inline SVG path for the trend line, rendering the `watch_rate` and `ctr` values across multiple snapshots from `get_metrics`)

**View 2: Scenario Aggregation ("scenarios" tab)**
- Three cards: S1, S2, S3 -- each showing avg watch_rate, avg CTR, avg CVR
- Clicking a card filters the view to that scenario's videos (switch to "videos" tab with filter applied)

**View 3: Platform Comparison ("platforms" tab)**
- Side-by-side comparison: TikTok vs Shopify
- For each platform: avg watch_rate, avg CTR, avg CVR, avg followers_gained (TikTok), avg sales (Shopify)
- Grouped by scenario: each row is a (platform, scenario) pair

**Implementation Details:**
- Import `fetchDashboardOverview`, `fetchVideoMetrics`, `API_BASE` from `./api`
- Use `useEffect` to fetch from `API_BASE + "/dashboard/overview?scenario=...&platform=...&hours=...`
- Use `useMemo` for client-side filtering when switching views
- Use inline SVG for the trend line charts (no external chart library -- keep dependency-free)
- Maintain the `apple-card`, `apple-btn` design language from existing components
- Empty state when no published videos exist: show "No published videos yet" with a prompt to publish from MediaView

#### 3.2 `web/src/components/PublishPanel.tsx` -- New Component

**Purpose**: Publish operation UI embedded in the Media tab of OneShotResultView.

**Structure:**

```tsx
"use client";

import { useState } from "react";
import { useI18n } from "@/i18n/I18nProvider";
import { publishVideo } from "./api";

interface PublishPanelProps {
  videoPath: string;
  metadata: {
    video_id: string;
    scenario: string;
    title?: string;
    hook_text?: string;
    hashtags?: string[];
    product_name?: string;
    description?: string;
  };
  onPublished?: (result: any) => void;
}

interface PublishProgress {
  tiktok: "idle" | "uploading" | "processing" | "done" | "error";
  shopify: "idle" | "uploading" | "processing" | "done" | "error";
}
```

**States to handle:**
- **Idle**: Platform checkboxes + editable title/description + "Publish" button
- **Publishing**: Per-platform progress indicators with spinner + status text
- **Done**: Success indicators with post_url links + "View Dashboard" button
- **Error**: Error message + retry button per platform
- **No platforms selected**: Button disabled with tooltip "Select at least one platform"

**API call:** `POST /publish/{video_id}` with body `{ platforms: [...], metadata: {...} }`

### Files to Modify

#### 3.3 `web/src/components/OneShotResultView.tsx` -- Add Dashboard Tab + Wire PublishPanel

**Modification 1: Add "performance" tab**

Add after the "quality" tab entry in the `TABS` array (around line 33 in the current file). The tab key is `"performance"`, the label is `t("result.tab.performance")`.

```tsx
const TABS = [
  // ... existing tabs through "quality" ...
  { id: "quality", label: t("result.tab.quality"), count: audit ? (audit.criteria?.length || 0) : 0, icon: "..." },
  // NEW:
  { id: "performance", label: t("result.tab.performance"), count: 0, icon: "..." },
  { id: "raw", label: t("result.tab.raw"), count: 0, icon: "..." },
];
```

**Modification 2: Add tab rendering**

Add in the tab content switch block (inside the `<div className="p-4 space-y-2 min-h-[200px]">` section):

```tsx
{tab === "performance" && <PerformanceDashboard scenario={scenario} />}
```

**Modification 3: Wire PublishPanel into MediaView**

Inside the `MediaView` component, replace or augment the existing "Platform Distribution" section (the `<div className="apple-card p-3 bg-[#fafafc]">` that contains `PlatformPublishRow`). The PublishPanel replaces the per-platform publish buttons:

```tsx
{/* Platform Distribution -- PublishPanel */}
<div className="apple-card p-3 bg-[#fafafc]">
  <div className="flex items-center gap-2 mb-2">
    <div className="w-6 h-6 rounded-md bg-[#7CB342]/10 flex items-center justify-center">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#7CB342" strokeWidth="2">
        <polyline points="17 1 21 5 17 9" />
        <path d="M3 11V9a4 4 0 0 1 4-4h14" />
        <polyline points="7 23 3 19 7 15" />
        <path d="M21 13v2a4 4 0 0 1-4 4H3" />
      </svg>
    </div>
    <p className="text-[11px] font-semibold text-[#1d1d1f]">{t("result.platformDistribution")}</p>
  </div>
  <PublishPanel
    videoPath={finalVideo}
    metadata={{
      video_id: result?.run_id || `video-${Date.now()}`,
      scenario,
      title: briefs?.[0]?.product_name || briefs?.[0]?.brand_name || "",
      hook_text: scripts?.[0]?.segments?.[0]?.description || "",
      hashtags: briefs?.[0]?.tags || [],
      product_name: briefs?.[0]?.product_name || "",
      description: briefs?.[0]?.description || "",
    }}
    onPublished={(res) => {
      // Optionally refresh or show a message
    }}
  />
</div>
```

The existing `PlatformPublishRow` function can be removed from `OneShotResultView.tsx` since PublishPanel replaces its functionality. The `PLATFORM_ICON_MAP` constant can also be removed if it is no longer used elsewhere in the file.

**Modification 4: Add import for PerformanceDashboard**

```tsx
import PerformanceDashboard from "./PerformanceDashboard";
import PublishPanel from "./PublishPanel";
```

#### 3.4 `web/src/components/api.ts` -- Add New API Functions

Add these four new functions. Place them after the existing `fetchPublishStatus` function:

```typescript
// -- Layer 5 Distribution API --

export async function publishVideo(
  videoId: string,
  platforms: string[],
  metadata: Record<string, any>
): Promise<any> {
  const res = await fetch(API_BASE + "/publish/" + encodeURIComponent(videoId), {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({ platforms, metadata }),
  });
  if (!res.ok) throw new Error("Publish failed (" + res.status + ")");
  return res.json();
}

export async function fetchVideoMetrics(
  videoId: string,
  platform?: string,
  limit?: number
): Promise<any> {
  const params = new URLSearchParams();
  if (platform) params.set("platform", platform);
  if (limit) params.set("limit", String(limit));
  const url = API_BASE + "/metrics/" + encodeURIComponent(videoId)
    + (params.toString() ? "?" + params.toString() : "");
  const res = await fetch(url, { headers: getHeaders(false) });
  if (!res.ok) throw new Error("Failed to fetch metrics (" + res.status + ")");
  return res.json();
}

export async function fetchDashboardOverview(
  scenario?: string,
  platform?: string,
  hours?: number
): Promise<any> {
  const params = new URLSearchParams();
  if (scenario) params.set("scenario", scenario);
  if (platform) params.set("platform", platform);
  if (hours) params.set("hours", String(hours));
  const url = API_BASE + "/dashboard/overview"
    + (params.toString() ? "?" + params.toString() : "");
  const res = await fetch(url, { headers: getHeaders(false) });
  if (!res.ok) throw new Error("Failed to fetch dashboard (" + res.status + ")");
  return res.json();
}

export async function triggerMetricsPull(): Promise<any> {
  const res = await fetch(API_BASE + "/metrics/pull", {
    method: "POST",
    headers: getHeaders(),
  });
  if (!res.ok) throw new Error("Metrics pull failed (" + res.status + ")");
  return res.json();
}
```

#### 3.5 `web/src/i18n/translations.ts` -- Add Dashboard and Publish i18n Keys

Add these keys to both `zh` and `en` locale blocks. Insert them after the existing `dist.*` keys:

```typescript
// Performance Dashboard (insert after dist.* section)
"result.tab.performance": "效果看板",
"dashboard.title": "效果看板",
"dashboard.view.videos": "视频列表",
"dashboard.view.scenarios": "场景聚合",
"dashboard.view.platforms": "平台对比",
"dashboard.noData": "暂无已发布视频",
"dashboard.filter.scenario": "场景筛选",
"dashboard.filter.platform": "平台筛选",
"dashboard.filter.timeRange": "时间范围",
"dashboard.filter.time24h": "24小时",
"dashboard.filter.time7d": "7天",
"dashboard.filter.time30d": "30天",
"dashboard.filter.timeAll": "全部",
"dashboard.col.videoId": "视频ID",
"dashboard.col.scenario": "场景",
"dashboard.col.platform": "平台",
"dashboard.col.watchRate": "完播率",
"dashboard.col.ctr": "点击率",
"dashboard.col.cvr": "转化率",
"dashboard.col.followers": "关注增量",
"dashboard.col.sales": "销量",
"dashboard.col.lastPulled": "最后更新",
"dashboard.ctr.high": "CTR 表现优秀",
"dashboard.ctr.low": "CTR 需要优化",
"dashboard.expand": "展开趋势",
"dashboard.collapse": "收起趋势",
"dashboard.trend.watchRate": "完播率趋势",
"dashboard.trend.ctr": "CTR 趋势",

// Publish Panel
"publish.title": "发布视频",
"publish.selectPlatforms": "选择发布平台",
"publish.platform.tiktok": "TikTok",
"publish.platform.shopify": "Shopify",
"publish.editTitle": "编辑标题",
"publish.editDescription": "编辑描述",
"publish.btnPublish": "发布",
"publish.btnPublishing": "发布中...",
"publish.status.uploading": "上传中...",
"publish.status.processing": "处理中...",
"publish.status.done": "已发布",
"publish.status.error": "发布失败",
"publish.retry": "重试",
"publish.viewPost": "查看帖子",
"publish.viewDashboard": "查看效果",
"publish.noPlatform": "请至少选择一个平台",
"publish.success": "发布成功",
```

And for the `en` block:

```typescript
"result.tab.performance": "Performance",
"dashboard.title": "Performance Dashboard",
"dashboard.view.videos": "Videos",
"dashboard.view.scenarios": "Scenarios",
"dashboard.view.platforms": "Platforms",
"dashboard.noData": "No published videos yet",
"dashboard.filter.scenario": "Scenario",
"dashboard.filter.platform": "Platform",
"dashboard.filter.timeRange": "Time Range",
"dashboard.filter.time24h": "24h",
"dashboard.filter.time7d": "7d",
"dashboard.filter.time30d": "30d",
"dashboard.filter.timeAll": "All",
"dashboard.col.videoId": "Video ID",
"dashboard.col.scenario": "Scenario",
"dashboard.col.platform": "Platform",
"dashboard.col.watchRate": "Watch Rate",
"dashboard.col.ctr": "CTR",
"dashboard.col.cvr": "CVR",
"dashboard.col.followers": "Followers",
"dashboard.col.sales": "Sales",
"dashboard.col.lastPulled": "Last Updated",
"dashboard.ctr.high": "CTR Good",
"dashboard.ctr.low": "CTR Needs Improvement",
"dashboard.expand": "Show Trend",
"dashboard.collapse": "Hide Trend",
"dashboard.trend.watchRate": "Watch Rate Trend",
"dashboard.trend.ctr": "CTR Trend",

"publish.title": "Publish Video",
"publish.selectPlatforms": "Select Platforms",
"publish.platform.tiktok": "TikTok",
"publish.platform.shopify": "Shopify",
"publish.editTitle": "Title",
"publish.editDescription": "Description",
"publish.btnPublish": "Publish",
"publish.btnPublishing": "Publishing...",
"publish.status.uploading": "Uploading...",
"publish.status.processing": "Processing...",
"publish.status.done": "Published",
"publish.status.error": "Publish Failed",
"publish.retry": "Retry",
"publish.viewPost": "View Post",
"publish.viewDashboard": "View Performance",
"publish.noPlatform": "Select at least one platform",
"publish.success": "Published Successfully",
```

### Self-Verification for Track 3

1. Run `cd /sessions/modest-zealous-allen/mnt/AI_vedio/web && npx tsc --noEmit` -- no type errors
2. Open the frontend in browser after backend is running, navigate to Stage 3 result view
3. Verify the "Performance" tab appears after "Quality" tab in the tab bar
4. Switch to Performance tab -- should show empty state ("No published videos yet")
5. Verify PublishPanel renders in the Media tab with platform checkboxes and title field
6. Verify all text appears in English (default locale)
7. Verify tab switching between all tabs still works correctly
8. Verify the PublishPanel has disabled button when no platform is selected

---

## Track 4: Integration + Verification

### Integration Steps

#### 4.1 Wire PublishPanel into OneShotResultView MediaView

- Replace the existing `PlatformPublishRow` section in `MediaView` (the `<div className="apple-card p-3 bg-[#fafafc]">` containing "Platform Distribution") with the new `PublishPanel` component
- Pass `finalVideo`, `metadata` from result (extract `video_id`, `scenario`, `title`, etc. from `result.briefs`, `result.scripts`)
- Remove the `PlatformPublishRow` function and `PLATFORM_ICON_MAP` from `OneShotResultView.tsx` since they are no longer needed
- Add imports for `PerformanceDashboard` and `PublishPanel`

#### 4.2 Mock Mode Verification

Verify that all features work without any API keys configured (no TIKTOK_ACCESS_TOKEN, no SHOPIFY_ACCESS_TOKEN):

1. **Publish Engine Mock Mode:**
   - Call `PublishEngine.publish()` without tokens
   - Verify it returns `PublishResult(success=True)` with mock post_id and URL
   - Verify no external HTTP calls are made (mock paths do not call `httpx` or `aiohttp`)

2. **Metrics Poller Mock Mode:**
   - Call `MetricsPoller._fetch_from_tiktok()` without token
   - Verify it returns deterministic mock metrics data
   - Call `MetricsPoller._fetch_from_shopify()` without token
   - Verify it returns deterministic mock metrics data

3. **API Endpoint Mock Mode:**
   - Start the FastAPI server without any platform API keys set
   - Call `POST /publish/{video_id}` with test data
   - Verify it returns 200 with mock success result
   - Call `GET /metrics/{video_id}` -- verify it returns empty metrics array gracefully
   - Call `GET /dashboard/overview` -- verify it returns empty totals gracefully
   - Call `POST /metrics/pull` -- verify it returns status completed

4. **Frontend Mock Mode:**
   - Open the frontend with the backend running in mock mode
   - Navigate to a completed S1 pipeline result
   - Verify PublishPanel shows platform checkboxes and "Publish" button
   - Click Publish -- verify it shows success state with a mock URL
   - Navigate to the Performance tab -- verify empty state is shown gracefully
   - Verify no console errors related to missing API keys

#### 4.3 Frontend-Backend API Consistency Check

Verify that the API contract is consistent between frontend and backend. For each pair, start the backend, call the endpoint with curl, and verify the response structure matches the frontend type expectations:

| Frontend call | Backend endpoint | Request shape | Response shape |
|---|---|---|---|
| `publishVideo(id, platforms, metadata)` | `POST /publish/{video_id}` | `{platforms: string[], metadata: object}` | `{video_id: string, results: [{success: bool, platform: string, post_id: string|null, post_url: string|null}]}` |
| `fetchVideoMetrics(id, platform?, limit?)` | `GET /metrics/{video_id}` | Query: `platform`, `limit` | `{video_id: string, metrics: MetricsSnapshot[]}` |
| `fetchDashboardOverview(s, p, hours?)` | `GET /dashboard/overview` | Query: `scenario`, `platform`, `hours` | `{totals, by_scenario[], by_platform[], top_videos[]}` |
| `triggerMetricsPull()` | `POST /metrics/pull` | `{}` | `{status: string}` |

**Verification script:**
```python
import asyncio, httpx
async def verify():
    base = "http://localhost:8001"
    headers = {"X-API-Key": "ai_video_demo_2026", "Content-Type": "application/json"}
    async with httpx.AsyncClient() as client:
        # 1. Publish
        r = await client.post(f"{base}/publish/test_video_1", json={
            "platforms": ["tiktok", "shopify"],
            "metadata": {"video_id": "test_video_1", "scenario": "S1", "title": "Test"}
        }, headers=headers)
        assert r.status_code == 200, f"Publish failed: {r.status_code}"
        data = r.json()
        assert "results" in data
        assert len(data["results"]) == 2
        print("1. POST /publish/ OK")

        # 2. Metrics
        r = await client.get(f"{base}/metrics/test_video_1", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert "video_id" in data and "metrics" in data
        print("2. GET /metrics/ OK")

        # 3. Dashboard
        r = await client.get(f"{base}/dashboard/overview", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert "totals" in data and "by_scenario" in data
        print("3. GET /dashboard/overview OK")

        # 4. Manual pull
        r = await client.post(f"{base}/metrics/pull", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert "status" in data
        print("4. POST /metrics/pull OK")

    print("All API consistency checks passed!")
asyncio.run(verify())
```

#### 4.4 Final Compilation Verification

```bash
# Backend -- Python compilation check
cd $(git rev-parse --show-toplevel)
python -m py_compile src/storage/metrics_repository.py
python -m py_compile src/tasks/metrics_poller.py
python -m py_compile src/connectors/publish_engine.py
python -m py_compile src/connectors/tiktok_connector.py
python -m py_compile src/connectors/shopify_connector.py
python -m py_compile src/api.py
python -m py_compile src/storage/db.py
python -m py_compile src/config.py
echo "All Python files compile OK"

# Frontend -- TypeScript check
cd web
npx tsc --noEmit
echo "TypeScript compilation OK"
```

### Rollback Strategy

If integration issues arise, the following files can be rolled back independently:

1. **Backend only** (no frontend changes): Revert `src/api.py`, all new `src/storage/metrics_repository.py`, `src/tasks/`, connector files, and `src/config.py`
2. **Frontend only** (no backend changes): Revert `web/src/components/PerformanceDashboard.tsx`, `PublishPanel.tsx`, and modifications to `OneShotResultView.tsx`, `api.ts`, `translations.ts`
3. **Partial backend**: The `video_metrics` table addition to `db.py` is additive-only and has zero impact on existing functionality. It can be left in place safely.

---

## Complete File Manifest

### New Files (6):

| File | Track | Lines (est.) | Purpose |
|------|-------|-------------|---------|
| `src/storage/metrics_repository.py` | 1 | 180-220 | Video metrics CRUD with SQL + PG dual-write |
| `src/tasks/__init__.py` | 1 | 1 | Package init |
| `src/tasks/metrics_poller.py` | 1 | 150-190 | Background poller with time-based strategy |
| `src/connectors/publish_engine.py` | 2 | 120-160 | Unified publish orchestrator |
| `web/src/components/PerformanceDashboard.tsx` | 3 | 350-450 | Three-view dashboard with filters |
| `web/src/components/PublishPanel.tsx` | 3 | 200-280 | Publish operation UI |

### Modified Files (9):

| File | Track | Change type | Modification |
|------|-------|-------------|--------------|
| `src/storage/db.py` | 1 | Add schema | Add `video_metrics` CREATE TABLE + indexes to `_create_sqlite_tables()`; add to `_REQUIRED_TABLES` |
| `src/connectors/tiktok_connector.py` | 2 | Add real API | Replace mock with real TikTok Content Posting + Insights API calls; keep mock fallback |
| `src/connectors/shopify_connector.py` | 2 | Add real API | Replace mock with real Shopify Admin GraphQL API calls; keep mock fallback |
| `src/config.py` | 2 | Add config | Add `SHOPIFY_STORE_URL` env var |
| `src/api.py` | 2 | Add endpoints | Add 4 new endpoints after existing distribution section |
| `web/src/components/OneShotResultView.tsx` | 3 | Add UI | Add "performance" tab, wire PublishPanel into MediaView, remove PlatformPublishRow |
| `web/src/components/api.ts` | 3 | Add API | Add 4 new API client functions |
| `web/src/i18n/translations.ts` | 3 | Add i18n | Add ~55 new i18n keys for dashboard and publish UI |

---

## Risk Register

| Risk | Impact | Mitigation | Track |
|------|--------|------------|-------|
| `video_metrics` table column mismatch between PG/SQLite | Data loss in one backend | Dual-write tests verify both backends produce same shape | 1 |
| TikTok API changes | Publish/monitor broken | Mock fallback always available; isolate API calls in `_fetch_from_tiktok` for easy swap | 2 |
| Shopify GraphQL schema changes | Media association breaks | GraphQL query version pinned to `2024-04`; mock fallback for testing | 2 |
| Frontend type mismatch with backend response shape | Runtime errors | API consistency check step in Track 4 verifies all 4 endpoints | 4 |
| PublishPanel crashes if result shape differs | Publish UI broken | Defensive access pattern (`result?.briefs?.[0]?.product_name`) used throughout | 3 |
| Metrics poller background task not cancelled | Resource leak | `stop()` method cancels asyncio task; lifecycle management via FastAPI lifespan | 1 |
| Existing DistributionView broken by changes | Regressions | DistributionView left entirely untouched -- no imports or dependencies changed | 4 |

---

## Sequencing Recommendation

Recommended implementation order for a single developer:

1. **Track 1 first** (creates the data foundation that everything else reads/writes)
2. **Track 2 second** (creates the publish API that both backend tests and frontend consume)
3. **Track 3 third** (frontend depends on Track 1+2 endpoints being available for full testing)
4. **Track 4 last** (integration verification across all layers)

For a team of 2+ developers, Tracks 1, 2, and 3 can all be worked on simultaneously with the understanding that frontend developers will need to mock the backend during development.

---

*Implementation Plan: v1.0 | Ready for execution*
