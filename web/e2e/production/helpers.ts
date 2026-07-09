import { expect, test, type APIRequestContext, type APIResponse } from "@playwright/test";

export const PRODUCTION_API_KEY = process.env.PLAYWRIGHT_API_KEY?.trim() ?? "";
const DEMO_API_KEY = "ai_video_demo_2026";

export function hasNonDemoProductionApiKey(): boolean {
  return PRODUCTION_API_KEY.length > 0 && PRODUCTION_API_KEY !== DEMO_API_KEY;
}

export function requireProductionApiKey(): string {
  test.skip(
    PRODUCTION_API_KEY.length === 0,
    "PLAYWRIGHT_API_KEY is required for authenticated production API smoke; do not use the demo key on production.",
  );
  test.skip(
    !hasNonDemoProductionApiKey(),
    "A non-demo PLAYWRIGHT_API_KEY is required for authenticated production API smoke.",
  );
  return PRODUCTION_API_KEY;
}

export function productionApiHeaders(extra: Record<string, string> = {}): Record<string, string> {
  return {
    "X-API-Key": requireProductionApiKey(),
    ...extra,
  };
}

export function isExpectedProductionPageNoise(message: string): boolean {
  const lower = message.toLowerCase();
  return (
    lower.includes("favicon")
    || lower.includes("hydrat")
    || lower.includes("404")
    || lower.includes("preload")
    || lower.includes("fonts.gstatic")
    || lower.includes("fonts.googleapis")
    || lower.includes("cors policy")
    || lower.includes("err_failed")
    || lower.includes("401")
    || lower.includes("unauthorized")
    || lower.includes("429")
    || lower.includes("too many requests")
    || lower.includes("net::err_failed")
    || lower.includes("net::err_connection_closed")
    || lower.includes("net::err_socket_not_connected")
  );
}

export async function delay(ms: number): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

export async function expectOkJsonWith429Retry(
  request: APIRequestContext,
  path: string,
  options: {
    headers?: Record<string, string>;
    attempts?: number;
    waitMs?: number;
  } = {},
): Promise<unknown> {
  const attempts = options.attempts ?? 4;
  const waitMs = options.waitMs ?? 1200;
  let lastResponse: APIResponse | null = null;

  for (let i = 0; i < attempts; i += 1) {
    const response = await request.get(path, { headers: options.headers });
    lastResponse = response;
    if (response.status() !== 429) {
      expect(response.status(), `${path} should return 2xx`).toBeLessThan(300);
      return response.json();
    }
    if (i < attempts - 1) {
      await delay(waitMs * (i + 1));
    }
  }

  expect(lastResponse?.status(), `${path} should not stay rate-limited after ${attempts} attempts`).not.toBe(429);
  throw new Error(`${path} remained rate-limited`);
}
