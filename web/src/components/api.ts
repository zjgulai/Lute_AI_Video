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
  // Production: use relative path via Nginx reverse proxy
  if (typeof window !== "undefined" && window.location.hostname !== "localhost") {
    return "/api";
  }
  const env = process.env.NEXT_PUBLIC_API_BASE_URL;
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

/** Demo mode detection.
 *
 * Priority: build-time env > localStorage override > hostname heuristic.
 * Production deployments set NEXT_PUBLIC_IS_DEMO=false at build time,
 * which takes precedence over any stale localStorage value from earlier
 * demo browsing.
 */
export function isDemoMode(): boolean {
  // 1. Build-time / runtime env is the canonical source of truth.
  const env = readEnv("NEXT_PUBLIC_IS_DEMO");
  if (env === "true") return true;
  if (env === "false") return false;

  // 2. localStorage allows user to manually toggle demo on isolated hosts.
  if (typeof window !== "undefined") {
    const stored = storageGet(STORAGE_KEYS.demoMode);
    if (stored === "true") return true;
    if (stored === "false") return false;
  }

  // 3. Hostname heuristic for static hosting (GitHub Pages / Vercel).
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

/** Build URL for GET /api/files (works with absolute dev base or production /api prefix). */
export function getFilesListUrl(): string {
  const base = getApiBase().replace(/\/$/, "");
  if (base.startsWith("http")) {
    return `${base}/api/files`;
  }
  return `${base}/files`;
}

// Backward-compatible constant — DEPRECATED, kept only for transition window.
// 新代码不要 import API_BASE,改用 apiFetch() / getApiBase()(每次调用都读
// localStorage,让 SettingsPanel 修改后立即生效)。
// 旧 API_BASE 是模块加载时常量,Settings 修改 base URL 后不会刷新。
/** @deprecated 用 apiFetch() 或 getApiBase() 替代。SettingsPanel 修改 base URL 后此常量不刷新。 */
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

// ── Request/Response Logging ──

// P1-B: 生产构建默认关日志,避免泄露请求体里的供应商 key / token。
// 调试时通过 localStorage.setItem('debug_api', '1') 显式开启。
function _initialLogEnabled(): boolean {
  if (typeof window === "undefined") return true; // SSR 默认开
  if (typeof process !== "undefined" && (process as any).env?.NODE_ENV === "production") {
    try {
      return localStorage.getItem("debug_api") === "1";
    } catch {
      return false;
    }
  }
  return true;
}

/** Whether API logging is enabled (生产默认关,开发默认开)。 */
let _apiLogEnabled = _initialLogEnabled();

/** Toggle API request/response logging at runtime. */
export function setApiLogging(enabled: boolean): void {
  _apiLogEnabled = enabled;
}

/** Check if API logging is currently enabled. */
export function isApiLoggingEnabled(): boolean {
  return _apiLogEnabled;
}

/** P1-B: 递归脱敏对象内的敏感字段,只替换值不删 key。
 *
 * 命中规则(字段名小写):key/token/secret/password/auth/api_keys/x-api-key/_key/apikey。
 * 输入任意值,原对象不被修改。返回脱敏副本。
 */
function redactSensitive(value: any, depth = 0): any {
  if (depth > 6) return "[redacted-depth-limit]";
  if (value == null) return value;
  if (Array.isArray(value)) {
    return value.map((v) => redactSensitive(v, depth + 1));
  }
  if (typeof value === "object") {
    const out: Record<string, any> = {};
    for (const [k, v] of Object.entries(value)) {
      const kLower = k.toLowerCase();
      if (
        kLower === "api_keys" ||
        kLower.includes("apikey") ||
        kLower.includes("api_key") ||
        kLower === "x-api-key" ||
        kLower.endsWith("_key") ||
        kLower === "key" ||
        kLower.includes("token") ||
        kLower.includes("secret") ||
        kLower.includes("password") ||
        kLower.includes("authorization") ||
        kLower === "auth"
      ) {
        out[k] = typeof v === "string" && v ? "***" : v;
      } else {
        out[k] = redactSensitive(v, depth + 1);
      }
    }
    return out;
  }
  return value;
}

/** P1-B: 给 JSON body 脱敏后返回 preview 字符串,无法解析时降级为长度提示。 */
function safeBodyPreview(body: BodyInit | null | undefined, maxLen = 400): string {
  if (typeof body !== "string" || !body) return "";
  if (body.startsWith("{") || body.startsWith("[")) {
    try {
      const parsed = JSON.parse(body);
      const redacted = JSON.stringify(redactSensitive(parsed));
      return redacted.length > maxLen ? redacted.slice(0, maxLen) + "..." : redacted;
    } catch {
      return body.length > maxLen ? "[non-json:" + body.length + "B]" : body;
    }
  }
  return body.length > maxLen ? body.slice(0, maxLen) + "..." : body;
}

/** Generate a short client-side trace ID. */
export function genTraceId(): string {
  return `c${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`;
}

/** Check if a URL is a media endpoint (body logging skipped). */
function isMediaUrl(url: string): boolean {
  return url.includes("/api/media/") || url.includes("/files");
}

/** Check if a URL is the health endpoint. */
function isHealthUrl(url: string): boolean {
  return url.endsWith("/health") || url.includes("/health?");
}

/** Native fetch reference (avoids recursion in apiFetch wrapper). */
const _nativeFetch = globalThis.fetch.bind(globalThis);

/**
 * P1-A: 统一 fetch wrapper — 自动注入 X-API-Key + 用 getApiBase() 把相对路径
 * 补全成绝对 URL,P1-B 日志脱敏请求体里的 api_keys / token / secret / password / auth。
 *
 * 业务调用方:
 *  - 相对路径(推荐):`apiFetch("/scenario/s1", {...})` → 自动拼 getApiBase()
 *  - 绝对(向后兼容):`apiFetch("http://...", {...})` → 不动
 *  - 默认 Content-Type=application/json,FormData 时自动跳过
 *
 * Log format:
 *   [HERMES:REQ]  POST /scenario/s1 trace_id=cxxxxx {body preview...}
 *   [HERMES:RES]  200 OK (2345ms) trace_id=cxxxxx→sxxxxx {response preview...}
 *   [HERMES:ERR]  500 Internal Server Error (120ms) trace_id=cxxxxx {error body...}
 *   [HERMES:ERR]  NETWORK_ERROR (0ms) trace_id=cxxxxx message
 */
export async function apiFetch(url: string, init?: RequestInit): Promise<Response> {
  // P1-A: 自动把相对路径补全 + 注入 auth header
  const absUrl = url.startsWith("http")
    ? url
    : getApiBase().replace(/\/$/, "") + (url.startsWith("/") ? url : "/" + url);
  const isFormData = typeof FormData !== "undefined" && init?.body instanceof FormData;
  const userHeaders = (init?.headers as Record<string, string>) || {};
  const mergedHeaders: Record<string, string> = {
    ...userHeaders,
    "X-API-Key": userHeaders["X-API-Key"] || getApiKey(),
  };
  // FormData 不要手设 Content-Type(浏览器自动加 boundary);其他默认 JSON
  if (
    !isFormData &&
    init?.body &&
    !mergedHeaders["Content-Type"] &&
    !mergedHeaders["content-type"]
  ) {
    mergedHeaders["Content-Type"] = "application/json";
  }

  if (!_apiLogEnabled) {
    return _nativeFetch(absUrl, { ...init, headers: mergedHeaders });
  }

  const traceId = genTraceId();
  const start = performance.now();
  const method = (init?.method || "GET").toUpperCase();
  const shortUrl = absUrl.replace(getApiBase(), "") || absUrl;
  const skipBody = isMediaUrl(absUrl);

  // Merge trace ID
  mergedHeaders["X-Client-Trace-Id"] = traceId;
  const mergedInit = { ...init, headers: mergedHeaders };

  // ── Log request ──
  if (isHealthUrl(absUrl)) {
    console.log(`[HERMES:HEALTH] ${method} ${shortUrl} trace_id=${traceId}`);
  } else {
    // P1-B: body 用 safeBodyPreview 脱敏
    const bodyPreview = skipBody ? "" : safeBodyPreview(init?.body);
    if (bodyPreview) {
      console.log(`[HERMES:REQ] ${method} ${shortUrl} trace_id=${traceId}`, bodyPreview);
    } else {
      console.log(`[HERMES:REQ] ${method} ${shortUrl} trace_id=${traceId}`);
    }
  }

  try {
    const res = await _nativeFetch(absUrl, mergedInit);
    const duration = Math.round(performance.now() - start);
    const serverTraceId = res.headers.get("X-Trace-Id") || res.headers.get("x-trace-id") || "";
    const traceChain = serverTraceId ? `${traceId}→${serverTraceId}` : traceId;

    if (!res.ok) {
      // Error response
      let errText = "";
      if (!skipBody) {
        try {
          errText = await res.clone().text();
        } catch {
          errText = "[unreadable]";
        }
      }
      console.error(
        `[HERMES:ERR] ${res.status} ${res.statusText} (${duration}ms) trace_id=${traceChain}`,
        errText.slice(0, 500) || "[no body]"
      );
      return res;
    }

    // Success response
    if (isHealthUrl(absUrl)) {
      console.log(`[HERMES:HEALTH] ${res.status} OK (${duration}ms) trace_id=${traceChain}`);
    } else if (skipBody) {
      console.log(`[HERMES:RES] ${res.status} ${res.statusText} (${duration}ms) trace_id=${traceChain} [media/binary]`);
    } else {
      const contentType = res.headers.get("content-type") || "";
      if (contentType.includes("application/json")) {
        try {
          const text = await res.clone().text();
          // P1-B: response body 也走脱敏(后端可能 echo api_keys)
          const preview = safeBodyPreview(text);
          console.log(`[HERMES:RES] ${res.status} ${res.statusText} (${duration}ms) trace_id=${traceChain}`, preview);
        } catch {
          console.log(`[HERMES:RES] ${res.status} ${res.statusText} (${duration}ms) trace_id=${traceChain} [body unreadable]`);
        }
      } else {
        console.log(`[HERMES:RES] ${res.status} ${res.statusText} (${duration}ms) trace_id=${traceChain} [${contentType || "unknown content-type"}]`);
      }
    }

    return res;
  } catch (err: any) {
    const duration = Math.round(performance.now() - start);
    console.error(`[HERMES:ERR] NETWORK_ERROR (${duration}ms) trace_id=${traceId}`, err.message || "Unknown error");
    throw err;
  }
}

// ── Core pipeline APIs ──

export async function startPipeline(body: any, options?: { signal?: AbortSignal }): Promise<any> {
  const res = await apiFetch(getApiBase() + "/pipeline/start", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(body),
    signal: options?.signal,
  });
  if (!res.ok) throw new Error("Pipeline start failed (" + res.status + ")");
  return res.json();
}

export async function fetchState(threadId: string, options?: { signal?: AbortSignal }): Promise<any> {
  const res = await apiFetch(getApiBase() + "/pipeline/" + threadId + "/state", {
    headers: getHeaders(false),
    signal: options?.signal,
  });
  if (!res.ok) throw new Error("Failed to fetch state (" + res.status + ")");
  return res.json();
}

export async function submitReview(
  threadId: string,
  reviewNode: string,
  action: string,
  reviewerNotes: string,
  options?: { signal?: AbortSignal }
): Promise<any> {
  const res = await apiFetch(getApiBase() + "/pipeline/" + threadId + "/review/" + reviewNode, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({ action, reviewer_notes: reviewerNotes }),
    signal: options?.signal,
  });
  if (!res.ok) throw new Error("Review submit failed (" + res.status + ")");
  return res.json();
}

export async function fetchDistribution(threadId: string, options?: { signal?: AbortSignal }): Promise<any> {
  const res = await apiFetch(getApiBase() + "/pipeline/" + threadId + "/distribution", {
    headers: getHeaders(false),
    signal: options?.signal,
  });
  if (!res.ok) throw new Error("Failed to fetch distribution info (" + res.status + ")");
  return res.json();
}

export async function fetchOutput(threadId: string, options?: { signal?: AbortSignal }): Promise<any> {
  const res = await apiFetch(getApiBase() + "/pipeline/" + threadId + "/output", {
    headers: getHeaders(false),
    signal: options?.signal,
  });
  if (!res.ok) throw new Error("Failed to fetch output (" + res.status + ")");
  return res.json();
}

// ── Scenario pipelines (skill-based, no LangGraph) ──

export async function runS1ProductDirect(config: any, options?: { signal?: AbortSignal }): Promise<any> {
  const res = await apiFetch(getApiBase() + "/scenario/s1", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(config),
    signal: options?.signal,
  });
  if (!res.ok) throw new Error("S1 failed: " + res.statusText);
  return res.json();
}

export async function runS2BrandCampaign(body: {
  brand_package: any;
  target_platforms?: string[];
  target_languages?: string[];
  week?: string;
}, options?: { signal?: AbortSignal }): Promise<any> {
  const res = await apiFetch(getApiBase() + "/scenario/s2", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(body),
    signal: options?.signal,
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
}, options?: { signal?: AbortSignal }): Promise<any> {
  const res = await apiFetch(getApiBase() + "/scenario/s3", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(body),
    signal: options?.signal,
  });
  if (!res.ok) throw new Error("Influencer remix scenario failed (" + res.status + ")");
  return res.json();
}

export async function runS4LiveShoot(body: {
  footage_assets: any[];
  product_info: any;
  topic?: string;
  target_platforms?: string[];
}, options?: { signal?: AbortSignal }): Promise<any> {
  const res = await apiFetch(getApiBase() + "/scenario/s4", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(body),
    signal: options?.signal,
  });
  if (!res.ok) throw new Error("Live shoot scenario failed (" + res.status + ")");
  return res.json();
}

// ── S1 Step-by-step pipeline APIs ──

export async function startS1StepByStep(config: any, options?: { signal?: AbortSignal }): Promise<any> {
  const res = await apiFetch(getApiBase() + "/scenario/s1/start", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({ ...config, mode: "step_by_step" }),
    signal: options?.signal,
  });
  if (!res.ok) throw new Error("S1 step-by-step start failed: " + res.statusText);
  return res.json();
}

export async function runS1Step(label: string, stepName: string, options?: { signal?: AbortSignal }): Promise<any> {
  const res = await apiFetch(getApiBase() + "/scenario/s1/step/" + stepName, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({ label }),
    signal: options?.signal,
  });
  if (!res.ok) throw new Error("S1 step " + stepName + " failed: " + res.statusText);
  return res.json();
}

export async function regenerateS1Step(label: string, stepName: string, options?: { signal?: AbortSignal }): Promise<any> {
  const res = await apiFetch(getApiBase() + "/scenario/s1/regenerate", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({ label, step: stepName }),
    signal: options?.signal,
  });
  if (!res.ok) throw new Error("S1 regenerate " + stepName + " failed: " + res.statusText);
  return res.json();
}

export async function resumeS1(label: string, options?: { signal?: AbortSignal }): Promise<any> {
  const res = await apiFetch(getApiBase() + "/scenario/s1/resume", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({ label }),
    signal: options?.signal,
  });
  if (!res.ok) throw new Error("S1 resume failed: " + res.statusText);
  return res.json();
}

export async function fetchS1State(label: string, options?: { signal?: AbortSignal }): Promise<any> {
  const res = await apiFetch(getApiBase() + "/scenario/s1/state/" + label, {
    headers: getHeaders(false),
    signal: options?.signal,
  });
  if (!res.ok) throw new Error("S1 fetch state failed (" + res.status + ")");
  return res.json();
}

export async function updateS1State(label: string, updates: any, options?: { signal?: AbortSignal }): Promise<any> {
  const res = await apiFetch(getApiBase() + "/scenario/s1/state/" + label, {
    method: "PUT",
    headers: getHeaders(),
    body: JSON.stringify(updates),
    signal: options?.signal,
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

export async function fetchAssets(options?: { signal?: AbortSignal }): Promise<any[]> {
  if (isDemoMode()) {
    const { DEMO_ASSETS } = await import("@/demo-data");
    return DEMO_ASSETS;
  }
  const res = await apiFetch(getFilesListUrl(), {
    headers: getHeaders(false),
    signal: options?.signal,
  });
  if (!res.ok) throw new Error("Failed to fetch assets list (" + res.status + ")");
  const data = await res.json();
  return data.files || [];
}

export function getMediaUrl(filePath: string, forceReal: boolean = false): string {
  if (!filePath) return "";
  if (!forceReal && isDemoMode()) {
    const name = filePath.replace(/\\/g, "/").split("/").pop() || "";
    const prefix = readEnv("NEXT_PUBLIC_ASSET_PREFIX") || "";
    return prefix + "/portfolio/" + encodeURIComponent(name);
  }
  let mediaRel = filePath.replace(/\\/g, "/");
  if (mediaRel.startsWith("/api/media/")) {
    mediaRel = mediaRel.slice("/api/media/".length);
  }
  try {
    mediaRel = decodeURIComponent(mediaRel);
  } catch {
    /* keep encoded segments */
  }
  const segments = mediaRel.split("/").filter(Boolean);
  const encodedPath = segments.map((s) => encodeURIComponent(s)).join("/");
  if (!encodedPath) return "";
  const base = getApiBase().replace(/\/$/, "");
  if (base.startsWith("http")) {
    return `${base}/api/media/${encodedPath}`;
  }
  return `/api/media/${encodedPath}`;
}

/** P1-8: Generate a short-lived signed URL for media access (15 min expiry).
 *
 * Use this when sharing media links externally or when stricter access
 * control is needed. Falls back to unsigned URL on signing failure.
 */
export async function getSignedMediaUrl(filePath: string): Promise<string> {
  if (!filePath) return "";
  let mediaRel = filePath.replace(/\\/g, "/");
  if (mediaRel.startsWith("/api/media/")) {
    mediaRel = mediaRel.slice("/api/media/".length);
  }
  try {
    mediaRel = decodeURIComponent(mediaRel);
  } catch {
    /* keep encoded segments */
  }
  const segments = mediaRel.split("/").filter(Boolean);
  const encodedPath = segments.map((s) => encodeURIComponent(s)).join("/");
  if (!encodedPath) return "";

  try {
    const base = getApiBase().replace(/\/$/, "");
    const res = await apiFetch(`${base}/api/media/sign?path=${encodeURIComponent(encodedPath)}`, {
      headers: getHeaders(),
    });
    if (res.ok) {
      const data = await res.json();
      return data.url || getMediaUrl(filePath);
    }
  } catch {
    /* fallback to unsigned */
  }
  return getMediaUrl(filePath);
}

// ── Connection test ──

export async function testConnection(options?: { signal?: AbortSignal }): Promise<{ ok: boolean; status: number; data?: any; error?: string }> {
  try {
    const res = await apiFetch(getApiBase() + "/health", {
      headers: getHeaders(false),
      signal: options?.signal,
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

// ── S5: Brand VLOG ──

export async function runS5BrandVlog(body: {
  brand_id: string;
  product_sku: any;
  scene_id: string;
  selected_models: any[];
  story_description: string;
  video_duration: number;
}, options?: { signal?: AbortSignal }): Promise<any> {
  const res = await apiFetch(getApiBase() + "/scenario/s5", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(body),
    signal: options?.signal,
  });
  if (!res.ok) throw new Error("Brand VLOG scenario failed (" + res.status + ")");
  return res.json();
}

// ── Distribution publishing APIs ──

export async function fetchPlatforms(options?: { signal?: AbortSignal }): Promise<any[]> {
  const res = await apiFetch(getApiBase() + "/distribution/platforms", {
    headers: getHeaders(false),
    signal: options?.signal,
  });
  if (!res.ok) throw new Error("Failed to fetch platform list (" + res.status + ")");
  const data = await res.json();
  return data.platforms || [];
}

export async function publishContent(platform: string, content: any, options?: { signal?: AbortSignal }): Promise<any> {
  const res = await apiFetch(getApiBase() + "/distribution/publish", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({ platform, content }),
    signal: options?.signal,
  });
  if (!res.ok) throw new Error("Publish failed (" + res.status + ")");
  return res.json();
}

export async function fetchPublishStatus(platform: string, postId: string, options?: { signal?: AbortSignal }): Promise<any> {
  const res = await apiFetch(
    getApiBase() + "/distribution/status/" + encodeURIComponent(platform) + "/" + encodeURIComponent(postId),
    { headers: getHeaders(false), signal: options?.signal }
  );
  if (!res.ok) throw new Error("Failed to fetch status (" + res.status + ")");
  return res.json();
}

// ── Layer 5: Publish, Metrics, Dashboard APIs ──

export async function publishVideo(videoId: string, platforms: string[], metadata: any, options?: { signal?: AbortSignal }): Promise<any> {
  const res = await apiFetch(getApiBase() + "/publish/" + videoId, {
    method: "POST", headers: getHeaders(),
    body: JSON.stringify({ platforms, metadata }),
    signal: options?.signal,
  });
  if (!res.ok) throw new Error("Publish failed (" + res.status + ")");
  return res.json();
}

export async function fetchVideoMetrics(videoId: string, platform?: string, options?: { signal?: AbortSignal }): Promise<any> {
  const params = platform ? "?platform=" + platform : "";
  const res = await apiFetch(getApiBase() + "/metrics/" + videoId + params, { headers: getHeaders(false), signal: options?.signal });
  if (!res.ok) throw new Error("Failed to fetch metrics");
  return res.json();
}

export async function fetchDashboardOverview(scenario?: string, platform?: string, days?: number, options?: { signal?: AbortSignal }): Promise<any> {
  const params = new URLSearchParams();
  if (scenario) params.set("scenario", scenario);
  if (platform) params.set("platform", platform);
  if (days) params.set("days", String(days));
  const res = await apiFetch(getApiBase() + "/dashboard/overview?" + params.toString(), { headers: getHeaders(false), signal: options?.signal });
  if (!res.ok) throw new Error("Failed to fetch dashboard");
  return res.json();
}

// ── Fast Mode: direct text-to-video (no pipeline) ──

export interface FastModeResult {
  success: boolean;
  video_path: string;
  video_url: string;
  filename: string;
  llm_prompt: string;
  scene_description: string;
  user_prompt: string;
  duration_seconds: number;
  file_size_bytes: number;
  generation_time_ms: number;
  timing: { llm_ms: number; video_ms: number; tts_ms: number };
  model_info: { llm: string; video: string; tts: string | null };
  is_stub: boolean;
  tts_path: string | null;
  error?: string;
}

export async function generateFastMode(body: {
  user_prompt: string;
  duration: number;
  enable_tts: boolean;
}, options?: { signal?: AbortSignal }): Promise<FastModeResult> {
  const res = await apiFetch(getApiBase() + "/fast/generate", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(body),
    signal: options?.signal,
  });
  if (!res.ok) {
    const err = await res.text().catch(() => "Fast Mode generation failed");
    throw new Error(err);
  }
  return res.json();
}

// ═══════════════════════════════════════════════════════════════
// Wave 2: 标准化交互日志 — UI / STATE / PIPE
// ═══════════════════════════════════════════════════════════════

/** UI 交互日志 — 记录用户点击/切换/提交等操作 */
export function logUI(
  action: "CLICK" | "NAV" | "SUBMIT" | "TOGGLE" | "SELECT" | "INPUT" | "RESET",
  component: string,
  details?: Record<string, any>
) {
  const traceId = genTraceId();
  const detailStr = details ? JSON.stringify(details) : "";
  // eslint-disable-next-line no-console
  console.log(`[HERMES:UI]   ${action.padEnd(6)} ${component.padEnd(24)} trace=${traceId}${detailStr ? " " + detailStr : ""}`);
  return traceId;
}

/** Pipeline 生命周期日志 — 记录 pipeline 启动/步骤/完成/错误 */
export function logPipe(
  event: "START" | "STEP" | "GATE" | "COMPLETE" | "CANCEL" | "ERROR" | "RECOVER",
  details?: Record<string, any>
) {
  const traceId = genTraceId();
  const detailStr = details ? JSON.stringify(details) : "";
  const level = event === "ERROR" ? "error" : "log";
  // eslint-disable-next-line no-console
  console[level](`[HERMES:PIPE]  ${event.padEnd(8)} ${detailStr ? " " + detailStr : ""} trace=${traceId}`);
  return traceId;
}

/** 辅助：生成状态变化日志 */
export function logStateChange(store: string, key: string, oldVal: any, newVal: any) {
  const oldStr = oldVal === undefined || oldVal === null ? "null" : String(oldVal).slice(0, 40);
  const newStr = newVal === undefined || newVal === null ? "null" : String(newVal).slice(0, 40);
  // eslint-disable-next-line no-console
  console.log(`[HERMES:STATE] ${store}.${key.padEnd(20)} ${oldStr} → ${newStr}`);
}

/** 辅助：生成 bug 检测日志（用于断言失败时） */
export function logBug(assertion: string, expected: string, actual: string, context?: Record<string, any>) {
  const traceId = genTraceId();
  // eslint-disable-next-line no-console
  console.error(
    `[HERMES:BUG]   ASSERT_FAIL ${assertion} expected="${expected}" actual="${actual}" trace=${traceId}`,
    context || ""
  );
  return traceId;
}

/** 辅助：生成测试通过/失败日志 */
export function logTest(testId: string, passed: boolean, message?: string) {
  const status = passed ? "PASS" : "FAIL";
  const traceId = genTraceId();
  // eslint-disable-next-line no-console
  console[passed ? "log" : "error"](`[HERMES:TEST]  ${status.padEnd(4)} ${testId.padEnd(12)} ${message || ""} trace=${traceId}`);
  return traceId;
}
