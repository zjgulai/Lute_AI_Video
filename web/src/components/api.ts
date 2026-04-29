// AI Video Pipeline backend API helpers

// Deployment: set NEXT_PUBLIC_API_BASE_URL on Vercel/Netlify/etc.
// Local dev: falls back to localhost:8001
// Same-domain deploy: set to "" (empty) to use relative paths
const _envBase =
  typeof process !== "undefined"
    ? (process as any).env?.NEXT_PUBLIC_API_BASE_URL
    : undefined;

export const API_BASE =
  _envBase === undefined || _envBase === ""
    ? "http://localhost:8001"
    : String(_envBase);

// Backend API Key for authentication (must match backend API_KEY env var)
let _apiKey = process.env.NEXT_PUBLIC_API_KEY || "ai_video_demo_2026";

export function setApiKey(key: string) {
  _apiKey = key;
}

export function getApiKey(): string {
  return _apiKey;
}

function getHeaders(contentType = true): Record<string, string> {
  const headers: Record<string, string> = {};
  if (contentType) {
    headers["Content-Type"] = "application/json";
  }
  headers["X-API-Key"] = _apiKey;
  return headers;
}

export async function startPipeline(body: any): Promise<any> {
  const res = await fetch(API_BASE + "/pipeline/start", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error("Pipeline start failed (" + res.status + ")");
  return res.json();
}

export async function fetchState(threadId: string): Promise<any> {
  const res = await fetch(API_BASE + "/pipeline/" + threadId + "/state", {
    headers: getHeaders(false),
  });
  if (!res.ok) throw new Error("Failed to fetch state (" + res.status + ")");
  return res.json();
}

export async function submitReview(
  threadId: string,
  reviewNode: string,
  action: string,
  reviewerNotes: string
): Promise<any> {
  const res = await fetch(API_BASE + "/pipeline/" + threadId + "/review/" + reviewNode, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({ action, reviewer_notes: reviewerNotes }),
  });
  if (!res.ok) throw new Error("Review submit failed (" + res.status + ")");
  return res.json();
}

export async function fetchDistribution(threadId: string): Promise<any> {
  const res = await fetch(API_BASE + "/pipeline/" + threadId + "/distribution", {
    headers: getHeaders(false),
  });
  if (!res.ok) throw new Error("Failed to fetch distribution info (" + res.status + ")");
  return res.json();
}

export async function fetchOutput(threadId: string): Promise<any> {
  const res = await fetch(API_BASE + "/pipeline/" + threadId + "/output", {
    headers: getHeaders(false),
  });
  if (!res.ok) throw new Error("Failed to fetch output (" + res.status + ")");
  return res.json();
}

// ── Scenario pipelines (skill-based, no LangGraph) ──

export async function runS1ProductDirect(config: any): Promise<any> {
  const res = await fetch(API_BASE + "/scenario/s1", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(config),
  });
  if (!res.ok) throw new Error("S1 failed: " + res.statusText);
  return res.json();
}

export async function runS2BrandCampaign(body: {
  brand_package: any;
  target_platforms?: string[];
  target_languages?: string[];
  week?: string;
}): Promise<any> {
  const res = await fetch(API_BASE + "/scenario/s2", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error("Brand campaign scenario failed (" + res.status + ")");
  return res.json();
}

export async function runS3InfluencerRemix(body: {
  video_url: string;
  product: any;
  influencer_name?: string;
  brief_id?: string;
  video_duration?: number;
}): Promise<any> {
  const res = await fetch(API_BASE + "/scenario/s3", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error("Influencer remix scenario failed (" + res.status + ")");
  return res.json();
}

export async function runS4LiveShoot(body: {
  footage_assets: any[];
  product_info: any;
  topic?: string;
  target_platforms?: string[];
}): Promise<any> {
  const res = await fetch(API_BASE + "/scenario/s4", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error("Live shoot scenario failed (" + res.status + ")");
  return res.json();
}

// ── S1 Step-by-step pipeline APIs ──

export async function startS1StepByStep(config: any): Promise<any> {
  const res = await fetch(API_BASE + "/scenario/s1/start", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({ ...config, mode: "step_by_step" }),
  });
  if (!res.ok) throw new Error("S1 step-by-step start failed: " + res.statusText);
  return res.json();
}

export async function runS1Step(label: string, stepName: string): Promise<any> {
  const res = await fetch(API_BASE + "/scenario/s1/step/" + stepName, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({ label }),
  });
  if (!res.ok) throw new Error("S1 step " + stepName + " failed: " + res.statusText);
  return res.json();
}

export async function regenerateS1Step(label: string, stepName: string): Promise<any> {
  const res = await fetch(API_BASE + "/scenario/s1/regenerate", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({ label, step: stepName }),
  });
  if (!res.ok) throw new Error("S1 regenerate " + stepName + " failed: " + res.statusText);
  return res.json();
}

export async function resumeS1(label: string): Promise<any> {
  const res = await fetch(API_BASE + "/scenario/s1/resume", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({ label }),
  });
  if (!res.ok) throw new Error("S1 resume failed: " + res.statusText);
  return res.json();
}

export async function fetchS1State(label: string): Promise<any> {
  const res = await fetch(API_BASE + "/scenario/s1/state/" + label, {
    headers: getHeaders(false),
  });
  if (!res.ok) throw new Error("S1 fetch state failed (" + res.status + ")");
  return res.json();
}

export async function updateS1State(label: string, updates: any): Promise<any> {
  const res = await fetch(API_BASE + "/scenario/s1/state/" + label, {
    method: "PUT",
    headers: getHeaders(),
    body: JSON.stringify(updates),
  });
  if (!res.ok) throw new Error("S1 update state failed (" + res.status + ")");
  return res.json();
}

export function downloadJson(data: any, filename: string) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export async function fetchAssets(): Promise<any[]> {
  if (IS_DEMO_MODE) {
    const { DEMO_ASSETS } = await import("@/demo-data");
    return DEMO_ASSETS;
  }
  const res = await fetch(API_BASE + "/api/files", {
    headers: getHeaders(false),
  });
  if (!res.ok) throw new Error("Failed to fetch assets list (" + res.status + ")");
  const data = await res.json();
  return data.files || [];
}

// Detect demo mode (GitHub Pages / static deploy with no backend)
// NOTE: use exact `process.env.NEXT_PUBLIC_IS_DEMO` so Next.js DefinePlugin replaces it at build time.
const IS_DEMO_MODE =
  (typeof process !== "undefined" &&
    process.env.NEXT_PUBLIC_IS_DEMO === "true") ||
  (typeof window !== "undefined" &&
    (window.location.hostname.includes("github.io") ||
      window.location.hostname.endsWith(".vercel.app")));

export function getMediaUrl(filePath: string): string {
  if (!filePath) return "";
  const name = filePath.replace(/\\/g, "/").split("/").pop() || "";
  // Demo mode: serve from static public folder
  if (IS_DEMO_MODE) {
    const prefix = process.env.NEXT_PUBLIC_ASSET_PREFIX || "";
    // Check if file exists in portfolio (copied media assets)
    return prefix + "/portfolio/" + encodeURIComponent(name);
  }
  return API_BASE + "/api/media/" + encodeURIComponent(name);
}

// ── Distribution publishing APIs ──

export async function fetchPlatforms(): Promise<any[]> {
  const res = await fetch(API_BASE + "/distribution/platforms", {
    headers: getHeaders(false),
  });
  if (!res.ok) throw new Error("Failed to fetch platform list (" + res.status + ")");
  const data = await res.json();
  return data.platforms || [];
}

export async function publishContent(platform: string, content: any): Promise<any> {
  const res = await fetch(API_BASE + "/distribution/publish", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({ platform, content }),
  });
  if (!res.ok) throw new Error("Publish failed (" + res.status + ")");
  return res.json();
}

export async function fetchPublishStatus(platform: string, postId: string): Promise<any> {
  const res = await fetch(
    API_BASE + "/distribution/status/" + encodeURIComponent(platform) + "/" + encodeURIComponent(postId),
    { headers: getHeaders(false) }
  );
  if (!res.ok) throw new Error("Failed to fetch status (" + res.status + ")");
  return res.json();
}

// ── Layer 5: Publish, Metrics, Dashboard APIs ──

export async function publishVideo(videoId: string, platforms: string[], metadata: any): Promise<any> {
  const res = await fetch(API_BASE + "/publish/" + videoId, {
    method: "POST", headers: getHeaders(),
    body: JSON.stringify({ platforms, metadata }),
  });
  if (!res.ok) throw new Error("Publish failed (" + res.status + ")");
  return res.json();
}

export async function fetchVideoMetrics(videoId: string, platform?: string): Promise<any> {
  const params = platform ? "?platform=" + platform : "";
  const res = await fetch(API_BASE + "/metrics/" + videoId + params, { headers: getHeaders(false) });
  if (!res.ok) throw new Error("Failed to fetch metrics");
  return res.json();
}

export async function fetchDashboardOverview(scenario?: string, platform?: string, days?: number): Promise<any> {
  const params = new URLSearchParams();
  if (scenario) params.set("scenario", scenario);
  if (platform) params.set("platform", platform);
  if (days) params.set("days", String(days));
  const res = await fetch(API_BASE + "/dashboard/overview?" + params.toString(), { headers: getHeaders(false) });
  if (!res.ok) throw new Error("Failed to fetch dashboard");
  return res.json();
}
