import { test, expect, type Page } from "@playwright/test";

const API_KEY = process.env.PLAYWRIGHT_API_KEY || "ai_video_demo_2026";

const TOKEN_CONSUMING_ENDPOINT_PATTERNS = [
  /\/(?:api\/)?fast\/(?:generate|submit|status)/,
  /\/(?:api\/)?scenario\/[^/]+(?:$|\/(?:submit|start|step|resume|regenerate|gate))/,
  /\/(?:api\/)?pipeline\/(?:start|[^/]+\/(?:review|distribution|output))/,
  /\/(?:api\/)?distribution\/publish/,
  /\/publish\//,
  /\/api\/upload/,
];

const TOP_PAGES = [
  { path: "/", name: "Home" },
  { path: "/s1", name: "S1 Product Direct" },
  { path: "/s2", name: "S2 Brand Campaign" },
  { path: "/s3", name: "S3 Influencer Remix" },
  { path: "/s4", name: "S4 Live Shoot" },
  { path: "/s5", name: "S5 Brand VLOG" },
  { path: "/fast", name: "Fast Mode" },
  { path: "/settings", name: "Settings" },
  { path: "/works", name: "Works" },
];

function isInfraNoise(msg: string): boolean {
  const lower = msg.toLowerCase();
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
    || lower.includes("net::err_failed")
  );
}

function isTokenConsumingEndpoint(url: string): boolean {
  const pathname = new URL(url).pathname;
  return TOKEN_CONSUMING_ENDPOINT_PATTERNS.some((pattern) => pattern.test(pathname));
}

async function installTokenConsumptionGuard(page: Page): Promise<string[]> {
  const violations: string[] = [];
  await page.route("**/*", async (route) => {
    const request = route.request();
    if (!isTokenConsumingEndpoint(request.url())) {
      await route.continue();
      return;
    }

    const pathname = new URL(request.url()).pathname;
    violations.push(`${request.method().toUpperCase()} ${pathname}`);
    await route.fulfill({
      status: 451,
      contentType: "application/json",
      body: JSON.stringify({ error: "Production non-token smoke blocked a token-consuming request" }),
    });
  });
  return violations;
}

test.describe("Production smoke — top-level pages", () => {
  for (const page of TOP_PAGES) {
    test(`${page.name} loads (${page.path})`, async ({ page: pw }) => {
      const errors: string[] = [];
      pw.on("pageerror", (e) => errors.push(e.message));
      pw.on("console", (msg) => {
        if (msg.type() === "error") errors.push(msg.text());
      });

      const response = await pw.goto(page.path, { waitUntil: "domcontentloaded" });
      expect(response).not.toBeNull();
      expect(response!.status()).toBeLessThan(400);

      await pw.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => {});

      await expect(pw.locator("body")).toBeVisible();

      const blocking = errors.filter((e) => !isInfraNoise(e));
      expect(blocking, `blocking errors on ${page.path}:\n${blocking.join("\n")}`).toEqual([]);
    });
  }
});

test.describe("Production smoke — backend API connectivity", () => {
  test("GET /api/portfolio/ returns valid JSON with files array", async ({ request }) => {
    const r = await request.get("/api/portfolio/?limit=5", {
      headers: { "X-API-Key": API_KEY },
    });
    expect(r.status()).toBe(200);
    const body = await r.json();
    expect(body).toHaveProperty("files");
    expect(Array.isArray(body.files)).toBe(true);
    expect(body).toHaveProperty("_meta");
    expect(body._meta).toHaveProperty("version");
  });

  test("GET /health returns version 0.2.x with media_tools all true", async ({ request }) => {
    const r = await request.get("/health");
    expect(r.status()).toBe(200);
    const body = await r.json();
    expect(body.status).toBe("ok");
    expect(body.version).toMatch(/^0\.\d+\.\d+/);
    expect(body).toHaveProperty("media_tools");
    expect(body.media_tools.ytdlp_available).toBe(true);
    expect(body.media_tools.whisper_available).toBe(true);
    expect(body.media_tools.clip_available).toBe(true);
  });

  test("_meta.version is consistent across /health and /api/portfolio", async ({ request }) => {
    const r1 = await request.get("/health");
    const r2 = await request.get("/api/portfolio/?limit=1", {
      headers: { "X-API-Key": API_KEY },
    });
    const v1 = (await r1.json()).version;
    const v2 = (await r2.json())._meta.version;
    expect(v1).toBe(v2);
  });
});

test.describe("Production smoke — navigation", () => {
  test("Settings page reachable via direct goto (handles session redirect)", async ({ page }) => {
    await page.goto("/settings", { waitUntil: "domcontentloaded" });
    await page.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => {});

    const url = page.url();
    expect(
      url.includes("/settings") || url.includes("session_expired"),
      `Expected /settings or session_expired redirect, got: ${url}`,
    ).toBe(true);
    await expect(page.locator("body")).toBeVisible();
  });

  test("Settings provider configuration is covered by default non-token smoke", async ({ page }) => {
    const violations = await installTokenConsumptionGuard(page);
    await page.addInitScript(() => {
      localStorage.setItem("ai_video_api_key", "ai_video_demo_2026");
      localStorage.setItem("ai_video_demo_mode", "true");
      localStorage.setItem("app-locale", "en");
      localStorage.setItem("ai-video-app-store", JSON.stringify({
        state: {
          activeScene: "product_direct",
          mode: "expert",
          pipelineMode: "step_by_step",
          showSplash: false,
          stage: "home",
          videoDuration: 30,
        },
        version: 0,
      }));
    });

    await page.goto("/settings", { waitUntil: "domcontentloaded" });
    await page.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => {});

    await expect(page.getByRole("dialog", { name: /Settings|设置/ })).toBeVisible();
    await page.getByRole("button", { name: /Providers|提供方/ }).click();
    await expect(page.getByText(/Provider API keys|Provider API Keys/)).toBeVisible();
    await expect(page.getByText(/Model route catalog|模型路由清单/)).toBeVisible();
    await expect(page.getByText("DEEPSEEK_API_KEY").first()).toBeVisible();
    await expect(page.getByText("POYO_API_KEY").first()).toBeVisible();
    await expect(page.getByText("SILICONFLOW_API_KEY").first()).toBeVisible();

    expect(violations, "default production settings smoke must not touch token-consuming endpoints").toEqual([]);
  });

  test("Fast Mode page reachable via direct goto (handles session redirect)", async ({ page }) => {
    await page.goto("/fast", { waitUntil: "domcontentloaded" });
    await page.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => {});

    const url = page.url();
    expect(
      url.includes("/fast") || url.includes("session_expired"),
      `Expected /fast or session_expired redirect, got: ${url}`,
    ).toBe(true);
    await expect(page.locator("body")).toBeVisible();
  });
});
