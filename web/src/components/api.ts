// AI Video Pipeline backend API helpers
// Runtime-configurable via localStorage (with cookie fallback) or build-time env vars.

const STORAGE_KEYS = {
  apiBase: "ai_video_api_base",
  apiKey: "ai_video_api_key",
  demoMode: "ai_video_demo_mode",
};

// ── P3-5: Cookie fallback for privacy / incognito mode ──

function setCookie(name: string, value: string, days = 365) {
  if (typeof document === "undefined") return;
  const d = new Date();
  d.setTime(d.getTime() + days * 24 * 60 * 60 * 1000);
  document.cookie = `${name}=${encodeURIComponent(value)};expires=${d.toUTCString()};path=/;SameSite=Lax`;
}

function getCookie(name: string): string | undefined {
  if (typeof document === "undefined") return undefined;
  const match = document.cookie.match(new RegExp("(?:^|; )" + name.replace(/([.$?*|{}()\[\]\\\/+^])/g, "\\$1") + "=([^;]*)"));
  return match ? decodeURIComponent(match[1]) : undefined;
}

function removeCookie(name: string) {
  if (typeof document === "undefined") return;
  document.cookie = `${name}=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/`;
}

/** Storage abstraction: localStorage with cookie fallback. */
function storageGet(key: string): string | null {
  if (typeof window === "undefined") return null;
  try {
    const val = localStorage.getItem(key);
    if (val !== null) return val;
  } catch (_) { /* localStorage unavailable (privacy mode) */ }
  return getCookie(key) ?? null;
}

function storageSet(key: string, value: string): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(key, value);
  } catch (_) { /* fall through to cookie */ }
  setCookie(key, value);
}

function storageRemove(key: string): void {
  if (typeof window === "undefined") return;
  try { localStorage.removeItem(key); } catch (_) {}
  removeCookie(key);
}

// ── Runtime configuration ──

function readEnv(key: string): string | undefined {
  if (typeof process === "undefined") return undefined;
  return (process as any).env?.[key] as string | undefined;
}

/** Backend API base URL (runtime-configurable via localStorage or env). */
export function getApiBase(): string {
  if (typeof window !== "undefined") {
    const stored = storageGet(STORAGE_KEYS.apiBase);
    if (stored) return stored;
  }
  const env = readEnv("NEXT_PUBLIC_API_BASE_URL");
  if (env) return env;
  return "http://localhost:8001";
}

export function setApiBase(url: string) {
  if (typeof window !== "undefined") {
    storageSet(STORAGE_KEYS.apiBase, url);
  }
}

/** Backend API Key (runtime-configurable via localStorage or env). */
export function getApiKey(): string {
  if (typeof window !== "undefined") {
    const stored = storageGet(STORAGE_KEYS.apiKey);
    if (stored) return stored;
  }
  return readEnv("NEXT_PUBLIC_API_KEY") || "ai_video_demo_2026";
}

export function setApiKey(key: string) {
  if (typeof window !== "undefined") {
    storageSet(STORAGE_KEYS.apiKey, key);
  }
}

/** Demo mode detection (runtime-configurable via localStorage or env/hostname). */
export function isDemoMode(): boolean {
  if (typeof window !== "undefined") {
    const stored = storageGet(STORAGE_KEYS.demoMode);
    if (stored === "true") return true;
    if (stored === "false") return false;
  }
  const env = readEnv("NEXT_PUBLIC_IS_DEMO");
  if (env === "true") return true;
  if (env === "false") return false;
  if (typeof window !== "undefined") {
    return (
      window.location.hostname.includes("github.io") ||
      window.location.hostname.endsWith(".vercel.app")
    );
  }
  return false;
}

export function setDemoMode(enabled: boolean) {
  if (typeof window !== "undefined") {
    storageSet(STORAGE_KEYS.demoMode, enabled ? "true" : "false");
  }
}

/** Reset all runtime config to defaults. */
export function resetApiConfig() {
  if (typeof window !== "undefined") {
    storageRemove(STORAGE_KEYS.apiBase);
    storageRemove(STORAGE_KEYS.apiKey);
    storageRemove(STORAGE_KEYS.demoMode);
  }
}

// Backward-compatible constant (reads from env/localStorage at call time via getApiBase)
export const API_BASE = getApiBase();

// ── Headers ──

export function getHeaders(contentType = true): Record<string, string> {
  const headers: Record<string, string> = {};
  if (contentType) {
    headers["Content-Type"] = "application/json";
  }
  headers["X-API-Key"] = getApiKey();
  return headers;
}

// ── Core pipeline APIs ──

export async function startPipeline(body: any): Promise<any> {
  const res = await fetch(getApiBase() + "/pipeline/start", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error("Pipeline start failed (" + res.status + ")");
  return res.json();
}

export async function fetchState(threadId: string): Promise<any> {
  const res = await fetch(getApiBase() + "/pipeline/" + threadId + "/state", {
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
  const res = await fetch(getApiBase() + "/pipeline/" + threadId + "/review/" + reviewNode, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({ action, reviewer_notes: reviewerNotes }),
  });
  if (!res.ok) throw new Error("Review submit failed (" + res.status + ")");
  return res.json();
}

export async function fetchDistribution(threadId: string): Promise<any> {
  const res = await fetch(getApiBase() + "/pipeline/" + threadId + "/distribution", {
    headers: getHeaders(false),
  });
  if (!res.ok) throw new Error("Failed to fetch distribution info (" + res.status + ")");
  return res.json();
}

export async function fetchOutput(threadId: string): Promise<any> {
  const res = await fetch(getApiBase() + "/pipeline/" + threadId + "/output", {
    headers: getHeaders(false),
  });
  if (!res.ok) throw new Error("Failed to fetch output (" + res.status + ")");
  return res.json();
}

// ── Scenario pipelines (skill-based, no LangGraph) ──

export async function runS1ProductDirect(config: any): Promise<any> {
  const res = await fetch(getApiBase() + "/scenario/s1", {
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
  const res = await fetch(getApiBase() + "/scenario/s2", {
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
  const res = await fetch(getApiBase() + "/scenario/s3", {
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
  const res = await fetch(getApiBase() + "/scenario/s4", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error("Live shoot scenario failed (" + res.status + ")");
  return res.json();
}

// ── S1 Step-by-step pipeline APIs ──

export async function startS1StepByStep(config: any): Promise<any> {
  const res = await fetch(getApiBase() + "/scenario/s1/start", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({ ...config, mode: "step_by_step" }),
  });
  if (!res.ok) throw new Error("S1 step-by-step start failed: " + res.statusText);
  return res.json();
}

export async function runS1Step(label: string, stepName: string): Promise<any> {
  const res = await fetch(getApiBase() + "/scenario/s1/step/" + stepName, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({ label }),
  });
  if (!res.ok) throw new Error("S1 step " + stepName + " failed: " + res.statusText);
  return res.json();
}

export async function regenerateS1Step(label: string, stepName: string): Promise<any> {
  const res = await fetch(getApiBase() + "/scenario/s1/regenerate", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({ label, step: stepName }),
  });
  if (!res.ok) throw new Error("S1 regenerate " + stepName + " failed: " + res.statusText);
  return res.json();
}

export async function resumeS1(label: string): Promise<any> {
  const res = await fetch(getApiBase() + "/scenario/s1/resume", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({ label }),
  });
  if (!res.ok) throw new Error("S1 resume failed: " + res.statusText);
  return res.json();
}

export async function fetchS1State(label: string): Promise<any> {
  const res = await fetch(getApiBase() + "/scenario/s1/state/" + label, {
    headers: getHeaders(false),
  });
  if (!res.ok) throw new Error("S1 fetch state failed (" + res.status + ")");
  return res.json();
}

export async function updateS1State(label: string, updates: any): Promise<any> {
  const res = await fetch(getApiBase() + "/scenario/s1/state/" + label, {
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
  if (isDemoMode()) {
    const { DEMO_ASSETS } = await import("@/demo-data");
    return DEMO_ASSETS;
  }
  const res = await fetch(getApiBase() + "/api/files", {
    headers: getHeaders(false),
  });
  if (!res.ok) throw new Error("Failed to fetch assets list (" + res.status + ")");
  const data = await res.json();
  return data.files || [];
}

export function getMediaUrl(filePath: string): string {
  if (!filePath) return "";
  const name = filePath.replace(/\\/g, "/").split("/").pop() || "";
  // Demo mode: serve from static public folder
  if (isDemoMode()) {
    const prefix = readEnv("NEXT_PUBLIC_ASSET_PREFIX") || "";
    return prefix + "/portfolio/" + encodeURIComponent(name);
  }
  return getApiBase() + "/api/media/" + encodeURIComponent(name);
}

// ── Connection test ──

export async function testConnection(): Promise<{ ok: boolean; status: number; data?: any; error?: string }> {
  try {
    const res = await fetch(getApiBase() + "/health", {
      headers: getHeaders(false),
    });
    if (!res.ok) {
      return { ok: false, status: res.status, error: "HTTP " + res.status };
    }
    const data = await res.json().catch(() => ({}));
    return { ok: true, status: res.status, data };
  } catch (e: any) {
    return { ok: false, status: 0, error: e.message || "Network error" };
  }
}

// ── Distribution publishing APIs ──

export async function fetchPlatforms(): Promise<any[]> {
  const res = await fetch(getApiBase() + "/distribution/platforms", {
    headers: getHeaders(false),
  });
  if (!res.ok) throw new Error("Failed to fetch platform list (" + res.status + ")");
  const data = await res.json();
  return data.platforms || [];
}

export async function publishContent(platform: string, content: any): Promise<any> {
  const res = await fetch(getApiBase() + "/distribution/publish", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({ platform, content }),
  });
  if (!res.ok) throw new Error("Publish failed (" + res.status + ")");
  return res.json();
}

export async function fetchPublishStatus(platform: string, postId: string): Promise<any> {
  const res = await fetch(
    getApiBase() + "/distribution/status/" + encodeURIComponent(platform) + "/" + encodeURIComponent(postId),
    { headers: getHeaders(false) }
  );
  if (!res.ok) throw new Error("Failed to fetch status (" + res.status + ")");
  return res.json();
}

// ── Layer 5: Publish, Metrics, Dashboard APIs ──

export async function publishVideo(videoId: string, platforms: string[], metadata: any): Promise<any> {
  const res = await fetch(getApiBase() + "/publish/" + videoId, {
    method: "POST", headers: getHeaders(),
    body: JSON.stringify({ platforms, metadata }),
  });
  if (!res.ok) throw new Error("Publish failed (" + res.status + ")");
  return res.json();
}

export async function fetchVideoMetrics(videoId: string, platform?: string): Promise<any> {
  const params = platform ? "?platform=" + platform : "";
  const res = await fetch(getApiBase() + "/metrics/" + videoId + params, { headers: getHeaders(false) });
  if (!res.ok) throw new Error("Failed to fetch metrics");
  return res.json();
}

export async function fetchDashboardOverview(scenario?: string, platform?: string, days?: number): Promise<any> {
  const params = new URLSearchParams();
  if (scenario) params.set("scenario", scenario);
  if (platform) params.set("platform", platform);
  if (days) params.set("days", String(days));
  const res = await fetch(getApiBase() + "/dashboard/overview?" + params.toString(), { headers: getHeaders(false) });
  if (!res.ok) throw new Error("Failed to fetch dashboard");
  return res.json();
}
