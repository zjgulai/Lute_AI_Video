// AI Video Pipeline backend API helpers
// Runtime-configurable via localStorage (with cookie fallback) or build-time env vars.

import { errorMessage } from "@/lib/errors";
import type { ContinuityDiagnosticsPayload } from "@/lib/continuityDiagnostics";
import type { ReviewState } from "@/components/types";
import type { components } from "@/types/api.generated";
import {
  PROVIDER_API_KEY_NAMES,
  REQUEST_PROVIDER_API_KEY_NAMES,
  type ProviderApiKeyName,
} from "@/lib/modelProviderConfig";

const STORAGE_KEYS = {
  apiBase: "ai_video_api_base",
  apiKey: "ai_video_api_key",
  demoMode: "ai_video_demo_mode",
  providerConfig: "ai_video_provider_config",
};

// Direct references are required for Next.js client-side build-time inlining.
const BUILD_TIME_API_KEY = process.env.NEXT_PUBLIC_API_KEY || "";

type ScenarioRunResult = {
  label?: string;
  briefs?: Record<string, unknown>[];
  scripts?: Record<string, unknown>[];
  thumbnail_image_paths?: string[];
  final_video_path?: string;
  video_duration?: number;
  audit_report?: { overall_score?: number };
};

type PipelineStepState = Record<string, unknown> & {
  status?: string;
  output?: unknown;
};

type StepRunnerState = Record<string, unknown> & {
  current_step?: string | null;
  gates?: Record<string, Record<string, unknown> & { status?: string }>;
  steps?: Record<string, PipelineStepState>;
};

type StepRunnerResponse = Record<string, unknown> & {
  label: string;
  state?: StepRunnerState;
  data?: unknown;
  steps?: Record<string, PipelineStepState>;
};

type PublishResult = Record<string, unknown> & {
  platform: string;
  success: boolean;
  post_id?: string;
  post_url?: string;
  error?: string;
};

type DistributionResponse = {
  distribution_plans?: Array<Record<string, unknown>>;
};

export type ModelProviderConfig = {
  apiKeys: Partial<Record<ProviderApiKeyName, string>>;
  enabledProviders?: Partial<Record<ProviderApiKeyName, boolean>>;
  updatedAt?: string;
};

type DashboardOverview = {
  videos: Array<{
    video_id: string;
    title: string;
    scenario: string;
    platform: string;
    ctr: number;
    cvr: number;
    watch_rate: number;
    followers_gained: number;
    sales: number;
    views: number;
    history?: { pulled_at: string; ctr: number; watch_rate: number }[];
  }>;
  scenarios: Array<{
    scenario: string;
    avg_watch_rate: number;
    avg_ctr: number;
    avg_cvr: number;
    total_videos: number;
    total_sales: number;
  }>;
  platforms: Array<{
    platform: string;
    avg_ctr: number;
    avg_cvr: number;
    avg_watch_rate: number;
    total_views: number;
    scenario_breakdown: Record<string, { avg_ctr: number; avg_cvr: number; avg_watch_rate: number }>;
  }>;
};

export type ToolboxToolId = components["schemas"]["ToolboxToolId"];

export type ToolboxRunMode = "dry_run" | "authorized_live";

export type ToolboxRunStatus =
  | "not_configured"
  | "prepared"
  | "blocked"
  | "review_required"
  | "accepted_dry_run"
  | "authorized_live_ready"
  | "failed";

export type ToolboxPlatformTarget = {
  platform: string;
  aspect_ratio?: string;
  locale?: string;
  duration_seconds?: number;
};

export type ToolboxAssetRef = {
  asset_ref: string;
  asset_kind: "image" | "video" | "audio" | "text" | "structured_data" | "mixed";
  rights_ref?: string | null;
  source_token_ids?: string[];
};

export type ToolboxToolInput = Record<string, unknown> & {
  tool_id: ToolboxToolId;
};

export type ToolboxRequestPayload = {
  request_id: string;
  tool_id: ToolboxToolId;
  brand_id: string;
  platform_target: ToolboxPlatformTarget;
  brand_bundle_ref?: string | null;
  asset_refs?: ToolboxAssetRef[];
  target_scenario?: string | null;
  tool_input: ToolboxToolInput;
};

export type ToolboxToolSummary = {
  tool_id: ToolboxToolId;
  label: string;
  description?: string;
  output_types?: string[];
  injectable_scenarios?: string[];
  default_checks?: string[];
  evidence_level?: string;
};

export type ToolboxToolsResponse = {
  evidence_level: "L2-fixture-or-dry-run";
  tools: ToolboxToolSummary[];
};

export type ToolboxPlanResponse = {
  plan_id: string;
  request_id: string;
  tool_id: ToolboxToolId;
  mode: ToolboxRunMode;
  evidence_level: "L2-fixture-or-dry-run" | "L4-authorized-live";
  provider_call: boolean;
  delivery_accepted: boolean;
  provider_profile_id?: string | null;
  prompt_hash?: string | null;
  required_checks?: string[];
  artifact_manifest_id?: string | null;
  injection_target_refs?: string[];
};

export type ToolboxPromptPreviewResponse = {
  preview_id: string;
  request_id: string;
  tool_id: ToolboxToolId;
  prompt_hash?: string | null;
  prompt_preview_allowed: boolean;
  sanitized_prompt_blocks?: string[];
  compile_warnings?: string[];
  blocked_reasons?: string[];
};

export type ToolboxArtifact = {
  artifact_id: string;
  tool_id: ToolboxToolId;
  artifact_type: string;
  artifact_ref: string;
  source_job_id?: string | null;
  manifest_ref?: string | null;
  delivery_accepted: boolean;
  publish_allowed: boolean;
};

export type ToolboxInjectionTarget = {
  target_ref: string;
  scenario: string;
  step_name: string;
  artifact_refs: string[];
  contract_refs: string[];
  bundle_refs?: string[];
};

export type ToolboxJobRecord = {
  job_id: string;
  status: "prepared" | "blocked" | "submitted" | "failed" | "succeeded";
  delivery_accepted: boolean;
  publish_allowed: boolean;
  blocked_reasons?: string[];
  failure_reason?: string | null;
  artifact_paths?: Record<string, string>;
  spec?: Record<string, unknown>;
};

export type ToolboxRunResponse = {
  run_id: string;
  request_id: string;
  tool_id: ToolboxToolId;
  brand_id: string;
  brand_bundle_ref?: string | null;
  target_scenario?: string | null;
  asset_refs?: ToolboxAssetRef[];
  status: ToolboxRunStatus;
  plan: ToolboxPlanResponse;
  prompt_preview?: ToolboxPromptPreviewResponse | null;
  job_record?: ToolboxJobRecord | null;
  artifacts: ToolboxArtifact[];
  injection_targets?: ToolboxInjectionTarget[];
};

export type ToolboxRunsResponse = {
  evidence_level: "L2-fixture-or-dry-run";
  runs: ToolboxRunResponse[];
};

export type ToolboxArtifactsResponse = {
  run_id: string;
  tool_id: ToolboxToolId;
  artifacts: ToolboxArtifact[];
};

export type ToolboxInjectionDraftResponse = {
  draft_id: string;
  draft_ref: string;
  run_id: string;
  tool_id: ToolboxToolId;
  mode: "read_only";
  evidence_level: "L2-fixture-or-dry-run";
  state_write: boolean;
  provider_call: boolean;
  delivery_accepted: boolean;
  publish_allowed: boolean;
  injection_targets: ToolboxInjectionTarget[];
  artifact_refs: string[];
  contract_refs: string[];
  bundle_refs: string[];
  blocked_reasons?: string[];
  warnings?: string[];
};

export type ToolboxInjectionAuditCheck = {
  check_id: string;
  label: string;
  status: "passed" | "advisory" | "blocked";
  evidence_refs?: string[];
  message?: string | null;
};

export type ToolboxInjectionAuditSummaryResponse = {
  summary_id: string;
  run_id: string;
  tool_id: ToolboxToolId;
  evidence_level: "L2-fixture-or-dry-run";
  ready_for_scenario_injection: boolean;
  state_write: boolean;
  provider_call: boolean;
  delivery_accepted: boolean;
  publish_allowed: boolean;
  injection_draft_ref?: string | null;
  target_count: number;
  artifact_ref_count: number;
  contract_ref_count: number;
  bundle_ref_count: number;
  checks: ToolboxInjectionAuditCheck[];
  blocking_reasons?: string[];
  advisory_reasons?: string[];
};

export type ToolboxAuditSummariesResponse = {
  evidence_level: "L2-fixture-or-dry-run";
  summaries: ToolboxInjectionAuditSummaryResponse[];
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
  } catch { /* localStorage unavailable (privacy mode) */ }
  return getCookie(key) ?? null;
}

function storageSet(key: string, value: string): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(key, value);
    removeCookie(key);
    return;
  } catch { /* fall through to cookie */ }
  setCookie(key, value);
}

function storageRemove(key: string): void {
  if (typeof window === "undefined") return;
  try { localStorage.removeItem(key); } catch {}
  removeCookie(key);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function normalizeProviderConfig(value: unknown): ModelProviderConfig {
  if (!isRecord(value)) {
    return { apiKeys: {} };
  }
  const rawApiKeys = isRecord(value.apiKeys) ? value.apiKeys : {};
  const apiKeys: Partial<Record<ProviderApiKeyName, string>> = {};
  for (const keyName of PROVIDER_API_KEY_NAMES) {
    const rawValue = rawApiKeys[keyName];
    if (typeof rawValue === "string" && rawValue.trim()) {
      apiKeys[keyName] = rawValue.trim();
    }
  }
  const rawEnabledProviders = isRecord(value.enabledProviders) ? value.enabledProviders : {};
  const enabledProviders: Partial<Record<ProviderApiKeyName, boolean>> = {};
  for (const keyName of PROVIDER_API_KEY_NAMES) {
    const rawValue = rawEnabledProviders[keyName];
    if (typeof rawValue === "boolean") {
      enabledProviders[keyName] = rawValue;
    }
  }
  const updatedAt = typeof value.updatedAt === "string" ? value.updatedAt : undefined;
  const normalized: ModelProviderConfig = { apiKeys };
  if (Object.keys(enabledProviders).length > 0) {
    normalized.enabledProviders = enabledProviders;
  }
  if (updatedAt) {
    normalized.updatedAt = updatedAt;
  }
  return normalized;
}

export function getModelProviderConfig(): ModelProviderConfig {
  if (typeof window === "undefined") {
    return { apiKeys: {} };
  }
  const raw = storageGet(STORAGE_KEYS.providerConfig);
  if (!raw) {
    return { apiKeys: {} };
  }
  try {
    return normalizeProviderConfig(JSON.parse(raw));
  } catch {
    return { apiKeys: {} };
  }
}

export function setModelProviderConfig(config: ModelProviderConfig): void {
  if (typeof window === "undefined") return;
  const normalized = normalizeProviderConfig({
    ...config,
    updatedAt: new Date().toISOString(),
  });
  const hasProviderState =
    Object.keys(normalized.apiKeys).length > 0
    || Object.keys(normalized.enabledProviders ?? {}).length > 0;
  if (!hasProviderState) {
    storageRemove(STORAGE_KEYS.providerConfig);
    return;
  }
  storageSet(STORAGE_KEYS.providerConfig, JSON.stringify(normalized));
}

export function resetModelProviderConfig(): void {
  if (typeof window === "undefined") return;
  storageRemove(STORAGE_KEYS.providerConfig);
}

export function getProviderApiKeysForRequest(): Record<string, string> {
  const config = getModelProviderConfig();
  const apiKeys: Record<string, string> = {};
  for (const keyName of REQUEST_PROVIDER_API_KEY_NAMES) {
    if (config.enabledProviders?.[keyName] === false) {
      continue;
    }
    const value = config.apiKeys[keyName]?.trim();
    if (value) {
      apiKeys[keyName] = value;
    }
  }
  return apiKeys;
}

export function withProviderApiKeys(body: unknown): unknown {
  const apiKeys = getProviderApiKeysForRequest();
  if (Object.keys(apiKeys).length === 0 || !isRecord(body)) {
    return body;
  }
  const existing = isRecord(body.api_keys) ? body.api_keys : {};
  return {
    ...body,
    api_keys: {
      ...apiKeys,
      ...existing,
    },
  };
}

// ── Runtime configuration ──

function readEnv(key: string): string | undefined {
  if (typeof process === "undefined") return undefined;
  return (process as unknown as { env?: Record<string, string | undefined> }).env?.[key];
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

/** Backend API Key (runtime-configurable via localStorage or env).
 *  Returns "" when no key is configured — callers MUST handle the empty case
 *  (the backend will 401 on missing/invalid keys). The home page enforces a
 *  key-entry gate before allowing any creative-API request. */
export function getApiKey(): string {
  if (typeof window !== "undefined") {
    const stored = storageGet(STORAGE_KEYS.apiKey);
    if (stored) return stored;
  }
  return BUILD_TIME_API_KEY;
}

export function hasApiKey(): boolean {
  return getApiKey().trim().length > 0;
}

export function setApiKey(key: string) {
  if (typeof window !== "undefined") {
    const trimmed = key.trim();
    if (!trimmed) {
      storageRemove(STORAGE_KEYS.apiKey);
      return;
    }
    storageSet(STORAGE_KEYS.apiKey, trimmed);
  }
}

export function maskApiKeyForDisplay(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return "Not set";
  if (trimmed.length <= 8) return "Set";
  return `${trimmed.slice(0, 4)}····${trimmed.slice(-3)}`;
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
    storageRemove(STORAGE_KEYS.providerConfig);
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
  if (typeof process !== "undefined" && (process as unknown as { env?: { NODE_ENV?: string } }).env?.NODE_ENV === "production") {
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
function redactSensitive(value: unknown, depth = 0): unknown {
  if (depth > 6) return "[redacted-depth-limit]";
  if (value == null) return value;
  if (Array.isArray(value)) {
    return value.map((v) => redactSensitive(v, depth + 1));
  }
  if (typeof value === "object") {
    const out: Record<string, unknown> = {};
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

// P3-5: Default fetch timeout — 30s for most requests, 300s for long-running pipelines
const DEFAULT_FETCH_TIMEOUT = 30000;
const LONG_RUNNING_TIMEOUT = 300000;
const API_FETCH_MAX_RETRIES = 1;

/** Determine appropriate timeout for a URL. */
function _getTimeoutMs(url: string): number {
  if (url.includes("/scenario/") || url.includes("/pipeline/")) {
    return LONG_RUNNING_TIMEOUT;
  }
  return DEFAULT_FETCH_TIMEOUT;
}

/** Native fetch reference (avoids recursion in apiFetch wrapper). */
const _nativeFetch = globalThis.fetch.bind(globalThis);

/**
 * P1-A: 统一 fetch wrapper — 自动注入 X-API-Key + 用 getApiBase() 把相对路径
 * 补全成绝对 URL,P1-B 日志脱敏请求体里的 api_keys / token / secret / password / auth。
 *
 * P3-5: 增加默认 timeout(30s/300s) 和 retry(1 次,仅对网络错误和 5xx)。
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
/** Routes whose own purpose is auth probing — must NOT trigger session-expired redirect.
 *  Otherwise the gate's own probe creates a redirect loop. */
const AUTH_PROBE_PATHS = ["/api/admin/auth/", "/distribution/platforms"];

function _isAuthProbe(absUrl: string): boolean {
  return AUTH_PROBE_PATHS.some((p) => absUrl.includes(p));
}

let _authExpiryHandled = false;

function _maybeHandleAuthExpiry(res: Response, absUrl: string): void {
  if (res.status !== 401) return;
  if (_isAuthProbe(absUrl)) return;
  if (typeof window === "undefined") return;
  if (_authExpiryHandled) return;

  if (location.pathname.startsWith("/admin")) return;

  _authExpiryHandled = true;
  setApiKey("");
  const target = "/?session_expired=1";
  if (location.pathname !== "/" || !location.search.includes("session_expired")) {
    window.location.href = target;
  }
}

export type ApiFetchInit = RequestInit & {
  suppressAuthExpiryRedirect?: boolean;
};

export async function apiFetch(url: string, init?: ApiFetchInit): Promise<Response> {
  const { suppressAuthExpiryRedirect = false, ...requestInit } = init ?? {};
  // P1-A: 自动把相对路径补全 + 注入 auth header
  // 2026-05-09 dedup: when base ends with "/api" (production behind nginx) and
  // url already starts with "/api/" (e.g. /api/files, /api/admin/...), strip
  // the base prefix to avoid producing "/api/api/..." which nginx 404s.
  let absUrl: string;
  if (url.startsWith("http")) {
    absUrl = url;
  } else {
    const base = getApiBase().replace(/\/$/, "");
    const path = url.startsWith("/") ? url : "/" + url;
    absUrl = base.endsWith("/api") && path.startsWith("/api/")
      ? base.slice(0, -"/api".length) + path
      : base + path;
  }
  const isFormData = typeof FormData !== "undefined" && requestInit.body instanceof FormData;
  const userHeaders = (requestInit.headers as Record<string, string>) || {};
  const mergedHeaders: Record<string, string> = {
    ...userHeaders,
    "X-API-Key": userHeaders["X-API-Key"] || getApiKey(),
  };
  // FormData 不要手设 Content-Type(浏览器自动加 boundary);其他默认 JSON
  if (
    !isFormData &&
    requestInit.body &&
    !mergedHeaders["Content-Type"] &&
    !mergedHeaders["content-type"]
  ) {
    mergedHeaders["Content-Type"] = "application/json";
  }

  const traceId = genTraceId();
  const start = performance.now();
  const method = (requestInit.method || "GET").toUpperCase();
  const shortUrl = absUrl.replace(getApiBase(), "") || absUrl;
  const skipBody = isMediaUrl(absUrl);

  // Merge trace ID
  mergedHeaders["X-Client-Trace-Id"] = traceId;
  const mergedInit: RequestInit = { ...requestInit, headers: mergedHeaders };

  // P3-5: Apply timeout via AbortController (respect caller's signal)
  const timeoutMs = _getTimeoutMs(absUrl);
  let timeoutId: ReturnType<typeof setTimeout> | undefined;
  const abortController = new AbortController();
  if (!mergedInit.signal) {
    mergedInit.signal = abortController.signal;
    timeoutId = setTimeout(() => abortController.abort(new DOMException("Request timeout", "TimeoutError")), timeoutMs);
  }

  // ── Log request ──
  if (_apiLogEnabled) {
    if (isHealthUrl(absUrl)) {
      console.log(`[HERMES:HEALTH] ${method} ${shortUrl} trace_id=${traceId}`);
    } else {
      const bodyPreview = skipBody ? "" : safeBodyPreview(requestInit.body);
      if (bodyPreview) {
        console.log(`[HERMES:REQ] ${method} ${shortUrl} trace_id=${traceId}`, bodyPreview);
      } else {
        console.log(`[HERMES:REQ] ${method} ${shortUrl} trace_id=${traceId}`);
      }
    }
  }

  // P3-5: Inner fetch with retry logic
  let lastError: unknown;
  const maxRetries = isHealthUrl(absUrl) ? 0 : API_FETCH_MAX_RETRIES;
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      const res = await _nativeFetch(absUrl, mergedInit);
      if (timeoutId) clearTimeout(timeoutId);

      const duration = Math.round(performance.now() - start);
      const serverTraceId = res.headers.get("X-Trace-Id") || res.headers.get("x-trace-id") || "";
      const traceChain = serverTraceId ? `${traceId}→${serverTraceId}` : traceId;

      // P3-5: Retry on 5xx server errors
      if (!res.ok && res.status >= 500 && attempt < maxRetries) {
        if (_apiLogEnabled) {
          console.warn(`[HERMES:RETRY] ${res.status} ${res.statusText} (${duration}ms) trace_id=${traceChain} attempt=${attempt + 1}/${maxRetries + 1}`);
        }
        await new Promise(r => setTimeout(r, 1000 * (attempt + 1)));
        continue;
      }

      if (!res.ok) {
        let errText = "";
        if (!skipBody) {
          try { errText = await res.clone().text(); } catch { errText = "[unreadable]"; }
        }
        if (_apiLogEnabled) {
          console.error(
            `[HERMES:ERR] ${res.status} ${res.statusText} (${duration}ms) trace_id=${traceChain}`,
            errText.slice(0, 500) || "[no body]"
          );
        }
        if (!suppressAuthExpiryRedirect) {
          _maybeHandleAuthExpiry(res, absUrl);
        }
        return res;
      }

      if (_apiLogEnabled) {
        if (isHealthUrl(absUrl)) {
          console.log(`[HERMES:HEALTH] ${res.status} OK (${duration}ms) trace_id=${traceChain}`);
        } else if (skipBody) {
          console.log(`[HERMES:RES] ${res.status} ${res.statusText} (${duration}ms) trace_id=${traceChain} [media/binary]`);
        } else {
          const contentType = res.headers.get("content-type") || "";
          if (contentType.includes("application/json")) {
            try {
              const text = await res.clone().text();
              const preview = safeBodyPreview(text);
              console.log(`[HERMES:RES] ${res.status} ${res.statusText} (${duration}ms) trace_id=${traceChain}`, preview);
            } catch {
              console.log(`[HERMES:RES] ${res.status} ${res.statusText} (${duration}ms) trace_id=${traceChain} [body unreadable]`);
            }
          } else {
            console.log(`[HERMES:RES] ${res.status} ${res.statusText} (${duration}ms) trace_id=${traceChain} [${contentType || "unknown content-type"}]`);
          }
        }
      }
      return res;
    } catch (err: unknown) {
      lastError = err;
      const errName = err instanceof Error ? err.name : "";
      const isRetryable = errName === "TypeError" || errName === "TimeoutError" || errName === "AbortError";
      if (isRetryable && attempt < maxRetries) {
        if (_apiLogEnabled) {
          const duration = Math.round(performance.now() - start);
          console.warn(`[HERMES:RETRY] NETWORK_ERROR (${duration}ms) trace_id=${traceId} attempt=${attempt + 1}/${maxRetries + 1} ${errorMessage(err, "")}`);
        }
        await new Promise(r => setTimeout(r, 1000 * (attempt + 1)));
        continue;
      }
      if (timeoutId) clearTimeout(timeoutId);
      break;
    }
  }

  const duration = Math.round(performance.now() - start);
  if (_apiLogEnabled) {
    console.error(`[HERMES:ERR] NETWORK_ERROR (${duration}ms) trace_id=${traceId}`, (lastError as { message?: string } | undefined)?.message || "Unknown error");
  }
  throw lastError;
}

export interface ApiErrorInfo {
  status: number;
  message: string;
  fieldErrors: Record<string, string>;
  retryAfterSec: number | null;
}

export async function parseApiError(res: Response): Promise<ApiErrorInfo> {
  const info: ApiErrorInfo = {
    status: res.status,
    message: res.statusText || `HTTP ${res.status}`,
    fieldErrors: {},
    retryAfterSec: null,
  };

  if (res.status === 429) {
    const headerRetry = res.headers.get("Retry-After");
    if (headerRetry) {
      const n = parseInt(headerRetry, 10);
      if (Number.isFinite(n) && n > 0) info.retryAfterSec = n;
    }
  }

  let body: unknown = null;
  try {
    body = await res.clone().json();
  } catch {
    try {
      const text = await res.clone().text();
      if (text) info.message = text.slice(0, 300);
    } catch { /* unreadable */ }
    return info;
  }

  if (body && typeof body === "object") {
    const obj = body as Record<string, unknown>;
    if (typeof obj.detail === "string") {
      info.message = obj.detail;
    } else if (Array.isArray(obj.detail)) {
      const messages: string[] = [];
      for (const item of obj.detail) {
        if (!item || typeof item !== "object") continue;
        const e = item as Record<string, unknown>;
        const msg = typeof e.msg === "string" ? e.msg : "Invalid value";
        const loc = Array.isArray(e.loc) ? e.loc : [];
        const field = loc
          .filter((p) => typeof p === "string" && p !== "body" && p !== "query" && p !== "path")
          .join(".");
        if (field) {
          info.fieldErrors[field] = msg;
          messages.push(`${field}: ${msg}`);
        } else {
          messages.push(msg);
        }
      }
      if (messages.length > 0) info.message = messages.join("; ");
    }
    if (typeof obj.retry_after_sec === "number" && obj.retry_after_sec > 0) {
      info.retryAfterSec = obj.retry_after_sec;
    }
  }

  return info;
}

export class ApiError extends Error {
  info: ApiErrorInfo;
  constructor(info: ApiErrorInfo) {
    super(info.message);
    this.name = "ApiError";
    this.info = info;
  }
}

export function isApiError(e: unknown): e is ApiError {
  return e instanceof ApiError;
}

async function throwApiError(res: Response): Promise<never> {
  throw new ApiError(await parseApiError(res));
}

// ── Core pipeline APIs ──

/** @deprecated Use /scenario/s1 (StepRunner) instead. LangGraph proxy layer only. */
export async function startPipeline(body: unknown, options?: { signal?: AbortSignal }): Promise<unknown> {
  const res = await apiFetch("/pipeline/start", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(withProviderApiKeys(body)),
    signal: options?.signal,
  });
  if (!res.ok) throw new Error("Pipeline start failed (" + res.status + ")");
  return res.json();
}

/** @deprecated StepRunner pipelines do not use LangGraph checkpoint state. */
export async function fetchState(threadId: string, options?: { signal?: AbortSignal }): Promise<ReviewState> {
  const res = await apiFetch("/pipeline/" + threadId + "/state", {
    headers: getHeaders(false),
    signal: options?.signal,
  });
  if (!res.ok) throw new Error("Failed to fetch state (" + res.status + ")");
  return res.json();
}

/** @deprecated Use /scenario/{s}/gate/{label}/{gate_id}/approve instead. */
export async function submitReview(
  threadId: string,
  reviewNode: string,
  action: string,
  reviewerNotes: string,
  options?: { signal?: AbortSignal }
): Promise<ReviewState> {
  const res = await apiFetch("/pipeline/" + threadId + "/review/" + reviewNode, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({ action, reviewer_notes: reviewerNotes }),
    signal: options?.signal,
  });
  if (!res.ok) throw new Error("Review submit failed (" + res.status + ")");
  return res.json();
}

/** @deprecated Use /scenario/{s}/state/{label} instead. */
export async function fetchDistribution(threadId: string, options?: { signal?: AbortSignal }): Promise<DistributionResponse> {
  const res = await apiFetch("/pipeline/" + threadId + "/distribution", {
    headers: getHeaders(false),
    signal: options?.signal,
  });
  if (!res.ok) throw new Error("Failed to fetch distribution info (" + res.status + ")");
  return res.json();
}

/** @deprecated Use /scenario/{s}/state/{label} instead. */
export async function fetchOutput(threadId: string, options?: { signal?: AbortSignal }): Promise<unknown> {
  const res = await apiFetch("/pipeline/" + threadId + "/output", {
    headers: getHeaders(false),
    signal: options?.signal,
  });
  if (!res.ok) throw new Error("Failed to fetch output (" + res.status + ")");
  return res.json();
}

// ── Scenario pipelines (skill-based, no LangGraph) ──

export async function runS1ProductDirect(config: unknown, options?: { signal?: AbortSignal }): Promise<ScenarioRunResult> {
  const res = await apiFetch("/scenario/s1", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(withProviderApiKeys(config)),
    signal: options?.signal,
  });
  if (!res.ok) throw new ApiError(await parseApiError(res));
  return res.json();
}

/** @deprecated S2 is a thin wrapper around S1. Use runS1ProductDirect with brand_mode=true. */
export async function runS2BrandCampaign(body: {
  brand_package: unknown;
  target_platforms?: string[];
  target_languages?: string[];
  week?: string;
}, options?: { signal?: AbortSignal }): Promise<ScenarioRunResult> {
  const res = await apiFetch("/scenario/s2", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(withProviderApiKeys(body)),
    signal: options?.signal,
  });
  if (!res.ok) throw new Error("Brand campaign scenario failed (" + res.status + ")");
  return res.json();
}

/** @deprecated Use /scenario/s3 (StepRunner) instead. */
export async function runS3InfluencerRemix(body: {
  video_url: string;
  product: unknown;
  influencer_name?: string;
  brief_id?: string;
  video_duration?: number;
}, options?: { signal?: AbortSignal }): Promise<ScenarioRunResult> {
  const res = await apiFetch("/scenario/s3", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(withProviderApiKeys(body)),
    signal: options?.signal,
  });
  if (!res.ok) throw new Error("Influencer remix scenario failed (" + res.status + ")");
  return res.json();
}

export async function runS4LiveShoot(body: {
  footage_assets: unknown[];
  product_info: unknown;
  topic?: string;
  target_platforms?: string[];
}, options?: { signal?: AbortSignal }): Promise<ScenarioRunResult> {
  const res = await apiFetch("/scenario/s4", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(withProviderApiKeys(body)),
    signal: options?.signal,
  });
  if (!res.ok) throw new Error("Live shoot scenario failed (" + res.status + ")");
  return res.json();
}

// ── S1 Step-by-step pipeline APIs ──

export async function startS1StepByStep(config: unknown, options?: { signal?: AbortSignal }): Promise<StepRunnerResponse> {
  const res = await apiFetch("/scenario/s1/start", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(withProviderApiKeys({ ...(config as Record<string, unknown>), mode: "step_by_step" })),
    signal: options?.signal,
  });
  if (!res.ok) return throwApiError(res);
  return res.json();
}

export async function runS1Step(label: string, stepName: string, options?: { signal?: AbortSignal }): Promise<StepRunnerResponse> {
  const res = await apiFetch("/scenario/s1/step/" + stepName, {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({ label }),
    signal: options?.signal,
  });
  if (!res.ok) return throwApiError(res);
  return res.json();
}

export async function regenerateS1Step(label: string, stepName: string, options?: { signal?: AbortSignal }): Promise<StepRunnerResponse> {
  const res = await apiFetch("/scenario/s1/regenerate", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({ label, step: stepName }),
    signal: options?.signal,
  });
  if (!res.ok) return throwApiError(res);
  return res.json();
}

export async function resumeS1(label: string, options?: { signal?: AbortSignal }): Promise<StepRunnerResponse> {
  const res = await apiFetch("/scenario/s1/resume", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({ label }),
    signal: options?.signal,
  });
  if (!res.ok) return throwApiError(res);
  return res.json();
}

export async function fetchS1State(label: string, options?: { signal?: AbortSignal }): Promise<StepRunnerState> {
  const res = await apiFetch("/scenario/s1/state/" + label, {
    headers: getHeaders(false),
    signal: options?.signal,
  });
  if (!res.ok) return throwApiError(res);
  return res.json();
}

export async function updateS1State(label: string, updates: unknown, options?: { signal?: AbortSignal }): Promise<StepRunnerState> {
  const res = await apiFetch("/scenario/s1/state/" + label, {
    method: "PUT",
    headers: getHeaders(),
    body: JSON.stringify(updates),
    signal: options?.signal,
  });
  if (!res.ok) return throwApiError(res);
  return res.json();
}

export function downloadJson(data: unknown, filename: string) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export async function fetchAssets(options?: { signal?: AbortSignal }): Promise<unknown[]> {
  if (isDemoMode()) {
    const { DEMO_ASSETS } = await import("@/demo-data");
    return DEMO_ASSETS;
  }
  const res = await apiFetch("/api/files", {
    headers: getHeaders(false),
    signal: options?.signal,
  });
  if (!res.ok) throw new Error("Failed to fetch assets list (" + res.status + ")");
  const data = await res.json();
  return data.files || [];
}

const MEDIA_SCHEME_RE = /^[a-z][a-z0-9+.-]*:/i;

function decodeMediaPath(raw: string): string | null {
  let decoded = raw;
  for (let i = 0; i < 3; i++) {
    try {
      const next = decodeURIComponent(decoded);
      if (next === decoded) return decoded;
      decoded = next;
    } catch {
      return null;
    }
  }
  return decoded;
}

function hasUnsafeMediaInput(rawPath: string): boolean {
  const normalized = rawPath.trim().replace(/\\/g, "/");
  const decoded = decodeMediaPath(normalized);
  const candidates = decoded && decoded !== normalized ? [normalized, decoded] : [normalized];
  return candidates.some((path) => {
    if (!path || path.includes("\x00") || path.includes("?") || path.includes("#")) return true;
    if (path.startsWith("//") || MEDIA_SCHEME_RE.test(path)) return true;
    return path.split("/").some((segment) => segment === "." || segment === "..");
  });
}

function encodeSafeMediaPath(filePath: string): string {
  if (!filePath || hasUnsafeMediaInput(filePath)) return "";

  let mediaRel = filePath.trim().replace(/\\/g, "/");
  if (mediaRel.startsWith("/api/media/")) {
    mediaRel = mediaRel.slice("/api/media/".length);
  } else if (mediaRel.startsWith("api/media/")) {
    mediaRel = mediaRel.slice("api/media/".length);
  } else if (mediaRel.startsWith("/")) {
    return "";
  }

  const decoded = decodeMediaPath(mediaRel);
  if (!decoded) return "";
  mediaRel = decoded.startsWith("output/") ? decoded.slice("output/".length) : decoded;

  const segments = mediaRel.split("/");
  if (
    segments.length === 0 ||
    segments.some((segment) => !segment || segment === "." || segment === ".." || segment.includes(":"))
  ) {
    return "";
  }
  return segments.map((s) => encodeURIComponent(s)).join("/");
}

export function getMediaUrl(filePath: string, forceReal: boolean = false): string {
  if (!filePath || hasUnsafeMediaInput(filePath)) return "";
  if (!forceReal && isDemoMode()) {
    const name = filePath.trim().replace(/\\/g, "/").split("/").pop() || "";
    const prefix = readEnv("NEXT_PUBLIC_ASSET_PREFIX") || "";
    return prefix + "/portfolio/" + encodeURIComponent(name);
  }
  const encodedPath = encodeSafeMediaPath(filePath);
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
  const encodedPath = encodeSafeMediaPath(filePath);
  if (!encodedPath) return "";

  try {
    const res = await apiFetch(`/api/media/sign?path=${encodeURIComponent(encodedPath)}`, {
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

// ═══════════════════════════════════════════════════════════════
// Admin Panel API (session-cookie auth, no X-API-Key)
// ═══════════════════════════════════════════════════════════════

/**
 * Build a URL for the admin API surface.
 *
 * Admin routes are mounted at absolute paths like `/api/admin/auth/login` on the
 * backend (no router prefix stripping). Callers pass the full `/api/admin/...`
 * path. This helper handles the prod base = "/api" case where naive
 * `base + path` would produce "/api/api/admin/..." and nginx would 404.
 *
 * Exported so non-adminFetch callers (e.g. the Nav admin-session probe which
 * must NOT trigger the 401 redirect in `adminFetch`) can still construct the
 * same URL.
 */
export function buildAdminUrl(path: string): string {
  const base = getApiBase().replace(/\/$/, "");
  const normalizedPath = path.startsWith("/") ? path : "/" + path;
  return base.endsWith("/api") && normalizedPath.startsWith("/api/")
    ? base.slice(0, -"/api".length) + normalizedPath
    : base + normalizedPath;
}

/**
 * Admin API fetch — uses session cookie authentication.
 * Does NOT send X-API-Key header. Uses credentials: 'include' for HttpOnly cookie.
 * On 401, redirects to /admin/login.
 */
export async function adminFetch(
  path: string,
  init?: RequestInit
): Promise<Response> {
  const url = buildAdminUrl(path);

  const mergedInit: RequestInit = {
    ...init,
    credentials: "include",
    headers: {
      ...(init?.headers as Record<string, string> || {}),
    },
  };

  // Admin API does NOT send X-API-Key
  if (mergedInit.headers) {
    delete (mergedInit.headers as Record<string, string>)["X-API-Key"];
  }

  // CSRF double-submit: read admin_csrf cookie + send as X-CSRF-Token header.
  // Backend verify_csrf_token (src/routers/_admin_deps.py) compares cookie
  // value to header value on POST/PUT/DELETE/PATCH. SameSite=Lax cookie
  // already blocks cross-site POST, this is defense-in-depth.
  const method = (mergedInit.method || "GET").toUpperCase();
  if (method !== "GET" && method !== "HEAD" && method !== "OPTIONS") {
    if (typeof document !== "undefined") {
      const m = document.cookie.match(/(?:^|; )admin_csrf=([^;]+)/);
      if (m && mergedInit.headers) {
        (mergedInit.headers as Record<string, string>)["X-CSRF-Token"] = decodeURIComponent(m[1]);
      }
    }
  }

  try {
    const res = await fetch(url, mergedInit);

    if (res.status === 401 && typeof window !== "undefined") {
      // Session expired — redirect to login
      const currentPath = window.location.pathname;
      if (!currentPath.startsWith("/admin/login")) {
        window.location.href = "/admin/login";
      }
    }

    return res;
  } catch {
    throw new Error("Admin API unreachable");
  }
}

/**
 * Fetch JSON from admin API. Returns parsed data or throws on error.
 */
export async function adminFetchJson<T = unknown>(
  path: string,
  init?: RequestInit
): Promise<T> {
  const res = await adminFetch(path, init);
  if (!res.ok) {
    const errText = await res.text().catch(() => "Unknown error");
    throw new Error(errText || `Admin API error (${res.status})`);
  }
  return res.json();
}

// ── Connection test ──

export async function testConnection(options?: { signal?: AbortSignal }): Promise<{ ok: boolean; status: number; data?: unknown; error?: string }> {
  try {
    const res = await apiFetch("/health", {
      headers: getHeaders(false),
      signal: options?.signal,
    });
    if (!res.ok) {
      return { ok: false, status: res.status, error: "HTTP " + res.status };
    }
    const data = await res.json().catch(() => ({}));
    return { ok: true, status: res.status, data };
  } catch (e: unknown) {
    return { ok: false, status: 0, error: errorMessage(e, "Network error") };
  }
}

// ── S5: Brand VLOG ──

export async function runS5BrandVlog(body: {
  brand_id: string;
  product_sku: unknown;
  scene_id: string;
  selected_models: unknown[];
  story_description: string;
  video_duration: number;
  enable_media_synthesis?: unknown;
  continuity_mode?: unknown;
  continuity_generation_mode?: string;
  storyboard_grid?: string | number;
  clip_group_size?: number;
  transition_style?: string;
}, options?: { signal?: AbortSignal }): Promise<ScenarioRunResult> {
  const res = await apiFetch("/scenario/s5", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(withProviderApiKeys(body)),
    signal: options?.signal,
  });
  if (!res.ok) throw new ApiError(await parseApiError(res));
  return res.json();
}

// ── Unified Async Execution (Phase 1A) ──

/**
 * Submit a scenario for async background execution.
 * Returns immediately with { label, status, trace_id }.
 * Use getScenarioStatus() to poll for progress.
 */
export async function submitScenario(
  scenario: string,
  body: unknown,
  options?: { signal?: AbortSignal }
): Promise<{ label: string; status: string; trace_id: string }> {
  const res = await apiFetch("/scenario/" + scenario + "/submit", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(withProviderApiKeys(body)),
    signal: options?.signal,
  });
  if (!res.ok) throw new ApiError(await parseApiError(res));
  return res.json();
}

/**
 * Poll execution status for a pipeline run.
 * Returns { label, status, current_step, progress, gate_status, errors }.
 */
export async function getScenarioStatus(
  scenario: string,
  label: string,
  options?: { signal?: AbortSignal }
): Promise<{
  label: string;
  scenario: string;
  status: string;
  current_step: string | null;
  current_step_injection?: Record<string, unknown> | null;
  progress: number;
  pipeline_degraded: boolean;
  soft_degraded_reasons?: Array<{ step?: string; reason?: string; detail?: string }>;
  continuity_diagnostics?: ContinuityDiagnosticsPayload;
  gate_status: string | null;
  errors: string[];
  steps?: Record<string, unknown>;
  result?: unknown;
}> {
  const res = await apiFetch(`/scenario/${scenario}/status/${encodeURIComponent(label)}`, {
    headers: getHeaders(false),
    signal: options?.signal,
  });
  if (!res.ok) throw new Error(`Status check failed (${res.status})`);
  return res.json();
}

export async function fetchGateState(
  scenario: string,
  label: string,
  gateId: string,
  options?: { signal?: AbortSignal },
): Promise<{
  gate_id: string;
  label: string;
  status: string;
  candidates: unknown[];
  selected_ids: string[];
  approved: boolean;
  max_selections: number;
  after_step: string;
  continuity_diagnostics?: ContinuityDiagnosticsPayload;
}> {
  const res = await apiFetch(
    `/scenario/${scenario}/gate/${encodeURIComponent(label)}/${gateId}`,
    {
      headers: getHeaders(false),
      signal: options?.signal,
    },
  );
  if (!res.ok) throw new Error(`Failed to fetch gate state (${res.status})`);
  return res.json();
}

// ── Distribution publishing APIs ──

export async function fetchPlatforms(options?: { signal?: AbortSignal }): Promise<unknown[]> {
  const res = await apiFetch("/distribution/platforms", {
    headers: getHeaders(false),
    signal: options?.signal,
  });
  if (!res.ok) throw new Error("Failed to fetch platform list (" + res.status + ")");
  const data = await res.json();
  return data.platforms || [];
}

export async function publishContent(platform: string, content: unknown, options?: { signal?: AbortSignal }): Promise<Record<string, unknown>> {
  const res = await apiFetch("/distribution/publish", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify({ platform, content }),
    signal: options?.signal,
  });
  if (!res.ok) throw new Error("Publish failed (" + res.status + ")");
  return res.json();
}

export async function fetchPublishStatus(platform: string, postId: string, options?: { signal?: AbortSignal }): Promise<Record<string, unknown>> {
  const res = await apiFetch(
    getApiBase() + "/distribution/status/" + encodeURIComponent(platform) + "/" + encodeURIComponent(postId),
    { headers: getHeaders(false), signal: options?.signal }
  );
  if (!res.ok) throw new Error("Failed to fetch status (" + res.status + ")");
  return res.json();
}

// ── Layer 5: Publish, Metrics, Dashboard APIs ──

export async function publishVideo(videoId: string, platforms: string[], metadata: unknown, options?: { signal?: AbortSignal }): Promise<PublishResult | PublishResult[]> {
  const res = await apiFetch("/publish/" + videoId, {
    method: "POST", headers: getHeaders(),
    body: JSON.stringify({ platforms, metadata }),
    signal: options?.signal,
  });
  if (!res.ok) throw new Error("Publish failed (" + res.status + ")");
  return res.json();
}

export async function fetchVideoMetrics(videoId: string, platform?: string, options?: { signal?: AbortSignal }): Promise<Record<string, unknown>> {
  const params = platform ? "?platform=" + platform : "";
  const res = await apiFetch("/metrics/" + videoId + params, { headers: getHeaders(false), signal: options?.signal });
  if (!res.ok) throw new Error("Failed to fetch metrics");
  return res.json();
}

export async function fetchDashboardOverview(scenario?: string, platform?: string, days?: number, options?: { signal?: AbortSignal }): Promise<DashboardOverview> {
  const params = new URLSearchParams();
  if (scenario) params.set("scenario", scenario);
  if (platform) params.set("platform", platform);
  if (days) params.set("days", String(days));
  const res = await apiFetch("/dashboard/overview?" + params.toString(), { headers: getHeaders(false), signal: options?.signal });
  if (!res.ok) throw new Error("Failed to fetch dashboard");
  return res.json();
}

// ── AI Video 2.0 Toolbox dry-run APIs ──

function toolboxUrl(toolId: ToolboxToolId, action: "plan" | "prompt-preview" | "run"): string {
  return `/toolbox/${encodeURIComponent(toolId)}/${action}`;
}

function assertToolboxRequest(toolId: ToolboxToolId, body: ToolboxRequestPayload): void {
  if (body.tool_id !== toolId) {
    throw new Error(`Toolbox request mismatch: path=${toolId}, body=${body.tool_id}`);
  }
  if (body.tool_input?.tool_id !== toolId) {
    throw new Error(`Toolbox input mismatch: path=${toolId}, input=${String(body.tool_input?.tool_id)}`);
  }
}

export async function fetchToolboxTools(options?: { signal?: AbortSignal }): Promise<ToolboxToolsResponse> {
  const res = await apiFetch("/toolbox/tools", {
    headers: getHeaders(false),
    signal: options?.signal,
    suppressAuthExpiryRedirect: true,
  });
  if (!res.ok) throw new ApiError(await parseApiError(res));
  return res.json();
}

export async function planToolboxRun(
  toolId: ToolboxToolId,
  body: ToolboxRequestPayload,
  options?: { signal?: AbortSignal },
): Promise<ToolboxPlanResponse> {
  assertToolboxRequest(toolId, body);
  const res = await apiFetch(toolboxUrl(toolId, "plan"), {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(body),
    signal: options?.signal,
  });
  if (!res.ok) throw new ApiError(await parseApiError(res));
  return res.json();
}

export async function previewToolboxPrompt(
  toolId: ToolboxToolId,
  body: ToolboxRequestPayload,
  options?: { signal?: AbortSignal },
): Promise<ToolboxPromptPreviewResponse> {
  assertToolboxRequest(toolId, body);
  const res = await apiFetch(toolboxUrl(toolId, "prompt-preview"), {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(body),
    signal: options?.signal,
  });
  if (!res.ok) throw new ApiError(await parseApiError(res));
  return res.json();
}

export async function runToolboxDryRun(
  toolId: ToolboxToolId,
  body: ToolboxRequestPayload,
  options?: { signal?: AbortSignal },
): Promise<ToolboxRunResponse> {
  assertToolboxRequest(toolId, body);
  const res = await apiFetch(toolboxUrl(toolId, "run"), {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(body),
    signal: options?.signal,
  });
  if (!res.ok) throw new ApiError(await parseApiError(res));
  return res.json();
}

export async function fetchToolboxRun(
  runId: string,
  options?: { signal?: AbortSignal },
): Promise<ToolboxRunResponse> {
  const res = await apiFetch(`/toolbox/runs/${encodeURIComponent(runId)}`, {
    headers: getHeaders(false),
    signal: options?.signal,
    suppressAuthExpiryRedirect: true,
  });
  if (!res.ok) throw new ApiError(await parseApiError(res));
  return res.json();
}

export async function fetchToolboxRuns(
  options?: { limit?: number; toolId?: ToolboxToolId; signal?: AbortSignal },
): Promise<ToolboxRunsResponse> {
  const params = new URLSearchParams();
  if (options?.limit) params.set("limit", String(options.limit));
  if (options?.toolId) params.set("tool_id", options.toolId);
  const query = params.toString();
  const res = await apiFetch(`/toolbox/runs${query ? `?${query}` : ""}`, {
    headers: getHeaders(false),
    signal: options?.signal,
    suppressAuthExpiryRedirect: true,
  });
  if (!res.ok) throw new ApiError(await parseApiError(res));
  return res.json();
}

export async function fetchToolboxAuditSummaries(
  options?: { limit?: number; toolId?: ToolboxToolId; signal?: AbortSignal },
): Promise<ToolboxAuditSummariesResponse> {
  const params = new URLSearchParams();
  if (options?.limit) params.set("limit", String(options.limit));
  if (options?.toolId) params.set("tool_id", options.toolId);
  const query = params.toString();
  const res = await apiFetch(`/toolbox/runs/audit-summaries${query ? `?${query}` : ""}`, {
    headers: getHeaders(false),
    signal: options?.signal,
    suppressAuthExpiryRedirect: true,
  });
  if (!res.ok) throw new ApiError(await parseApiError(res));
  return res.json();
}

export async function fetchToolboxArtifacts(
  runId: string,
  options?: { signal?: AbortSignal },
): Promise<ToolboxArtifactsResponse> {
  const res = await apiFetch(`/toolbox/runs/${encodeURIComponent(runId)}/artifacts`, {
    headers: getHeaders(false),
    signal: options?.signal,
    suppressAuthExpiryRedirect: true,
  });
  if (!res.ok) throw new ApiError(await parseApiError(res));
  return res.json();
}

export async function previewToolboxInjectionDraft(
  runId: string,
  options?: { signal?: AbortSignal },
): Promise<ToolboxInjectionDraftResponse> {
  const res = await apiFetch(`/toolbox/runs/${encodeURIComponent(runId)}/inject`, {
    method: "POST",
    headers: getHeaders(),
    signal: options?.signal,
  });
  if (!res.ok) throw new ApiError(await parseApiError(res));
  return res.json();
}

export async function fetchToolboxAuditSummary(
  runId: string,
  options?: { signal?: AbortSignal },
): Promise<ToolboxInjectionAuditSummaryResponse> {
  const res = await apiFetch(`/toolbox/runs/${encodeURIComponent(runId)}/audit-summary`, {
    headers: getHeaders(false),
    signal: options?.signal,
    suppressAuthExpiryRedirect: true,
  });
  if (!res.ok) throw new ApiError(await parseApiError(res));
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
  const res = await apiFetch("/fast/generate", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(body),
    signal: options?.signal,
  });
  if (!res.ok) throw new ApiError(await parseApiError(res));
  return res.json();
}

export interface FastSubmitResponse {
  task_id: string;
  status: "queued";
  started_at_unix: number;
}

export interface FastStatusResponse {
  task_id: string;
  status: "running" | "done" | "failed";
  stage: "queued" | "llm" | "video" | "tts";
  elapsed_sec: number;
  result: FastModeResult | null;
  error: string | null;
}

export async function submitFastMode(body: {
  user_prompt: string;
  duration: number;
  enable_tts: boolean;
}, options?: { signal?: AbortSignal }): Promise<FastSubmitResponse> {
  const res = await apiFetch("/fast/submit", {
    method: "POST",
    headers: getHeaders(),
    body: JSON.stringify(body),
    signal: options?.signal,
  });
  if (!res.ok) throw new ApiError(await parseApiError(res));
  return res.json();
}

export async function fetchFastStatus(
  taskId: string,
  options?: { signal?: AbortSignal },
): Promise<FastStatusResponse> {
  const res = await apiFetch(`/fast/status/${encodeURIComponent(taskId)}`, {
    headers: getHeaders(false),
    signal: options?.signal,
  });
  if (!res.ok) throw new ApiError(await parseApiError(res));
  return res.json();
}

export async function pollFastStatus(
  taskId: string,
  opts?: {
    signal?: AbortSignal;
    onProgress?: (s: FastStatusResponse) => void;
    intervalMs?: number;
    maxWaitMs?: number;
  },
): Promise<FastModeResult> {
  const interval = opts?.intervalMs ?? 2000;
  const maxWait = opts?.maxWaitMs ?? 600_000;
  const start = Date.now();

  while (Date.now() - start < maxWait) {
    if (opts?.signal?.aborted) throw new DOMException("Aborted", "AbortError");
    const snap = await fetchFastStatus(taskId, { signal: opts?.signal });
    opts?.onProgress?.(snap);
    if (snap.status === "done" && snap.result) return snap.result;
    if (snap.status === "failed") {
      throw new Error(snap.error || "Fast Mode generation failed");
    }
    await new Promise((r) => setTimeout(r, interval));
  }
  throw new Error(`Fast Mode timed out after ${maxWait}ms`);
}

// ═══════════════════════════════════════════════════════════════
// Wave 2: 标准化交互日志 — UI / STATE / PIPE
// ═══════════════════════════════════════════════════════════════

/** UI 交互日志 — 记录用户点击/切换/提交等操作 */
export function logUI(
  action: "CLICK" | "NAV" | "SUBMIT" | "TOGGLE" | "SELECT" | "INPUT" | "RESET",
  component: string,
  details?: Record<string, unknown>
) {
  const traceId = genTraceId();
  const detailStr = details ? JSON.stringify(details) : "";
   
  console.log(`[HERMES:UI]   ${action.padEnd(6)} ${component.padEnd(24)} trace=${traceId}${detailStr ? " " + detailStr : ""}`);
  return traceId;
}

/** Pipeline 生命周期日志 — 记录 pipeline 启动/步骤/完成/错误 */
export function logPipe(
  event: "START" | "STEP" | "GATE" | "COMPLETE" | "CANCEL" | "ERROR" | "RECOVER",
  details?: Record<string, unknown>
) {
  const traceId = genTraceId();
  const detailStr = details ? JSON.stringify(details) : "";
  const level = event === "ERROR" ? "error" : "log";
   
  console[level](`[HERMES:PIPE]  ${event.padEnd(8)} ${detailStr ? " " + detailStr : ""} trace=${traceId}`);
  return traceId;
}

/** 辅助：生成状态变化日志 */
export function logStateChange(store: string, key: string, oldVal: unknown, newVal: unknown) {
  const oldStr = oldVal === undefined || oldVal === null ? "null" : String(oldVal).slice(0, 40);
  const newStr = newVal === undefined || newVal === null ? "null" : String(newVal).slice(0, 40);
   
  console.log(`[HERMES:STATE] ${store}.${key.padEnd(20)} ${oldStr} → ${newStr}`);
}

/** 辅助：生成 bug 检测日志（用于断言失败时） */
export function logBug(assertion: string, expected: string, actual: string, context?: Record<string, unknown>) {
  const traceId = genTraceId();
   
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
   
  console[passed ? "log" : "error"](`[HERMES:TEST]  ${status.padEnd(4)} ${testId.padEnd(12)} ${message || ""} trace=${traceId}`);
  return traceId;
}
