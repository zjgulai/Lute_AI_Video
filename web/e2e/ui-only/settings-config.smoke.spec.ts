import { expect, test, type Page, type Route } from "@playwright/test";

const GENERATION_ENDPOINT_PATTERNS = [
  /\/fast\/(?:generate|submit|status)/,
  /\/scenario\/[^/]+(?:$|\/(?:submit|start|step|resume|regenerate|gate))/,
  /\/pipeline\/(?:start|[^/]+\/(?:review|distribution|output))/,
  /\/distribution\/publish/,
  /\/publish\//,
  /\/api\/upload/,
];

function isBackendUrl(url: string): boolean {
  const parsed = new URL(url);
  return url.includes("localhost:8001") || /\/api(?:\/|$)/.test(parsed.pathname);
}

function matchesGenerationEndpoint(url: string): boolean {
  const pathname = new URL(url).pathname;
  return GENERATION_ENDPOINT_PATTERNS.some((pattern) => pattern.test(pathname));
}

async function fulfillJson(route: Route, body: unknown) {
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function installSettingsUiGuards(page: Page): Promise<string[]> {
  const violations: string[] = [];

  await page.route("**/*", async (route) => {
    const request = route.request();
    const url = request.url();
    const method = request.method().toUpperCase();
    const pathname = new URL(url).pathname;

    if (matchesGenerationEndpoint(url) || !["GET", "HEAD", "OPTIONS"].includes(method)) {
      violations.push(`${method} ${pathname}`);
      await route.fulfill({
        status: 451,
        contentType: "application/json",
        body: JSON.stringify({ error: "Settings smoke blocked a token-consuming request" }),
      });
      return;
    }

    if (!isBackendUrl(url)) {
      await route.continue();
      return;
    }

    if (pathname.endsWith("/health")) {
      await fulfillJson(route, {
        status: "ok",
        version: "0.2.7-ui",
        media_tools: {
          ytdlp_available: true,
          whisper_available: true,
          clip_available: true,
        },
      });
      return;
    }

    if (pathname.endsWith("/api/admin/auth/session")) {
      await fulfillJson(route, { authenticated: false });
      return;
    }

    if (pathname.endsWith("/distribution/platforms")) {
      await fulfillJson(route, { platforms: [] });
      return;
    }

    if (pathname.endsWith("/portfolio/brand-presets")) {
      await fulfillJson(route, {
        brand: "momcozy",
        scraped_at: "2026-06-06T00:00:00Z",
        presets: [],
      });
      return;
    }

    if (pathname.endsWith("/portfolio/")) {
      await fulfillJson(route, { files: [], _meta: { version: "0.2.7-ui" } });
      return;
    }

    if (pathname.endsWith("/api/assets/influencers")) {
      await fulfillJson(route, { influencers: [] });
      return;
    }

    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ error: "Settings UI-only mock does not serve this backend route" }),
    });
  });

  return violations;
}

async function primeSettingsState(page: Page) {
  await page.addInitScript(() => {
    localStorage.clear();
    localStorage.setItem("ai_video_api_key", "ui_only_fake_key");
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
}

async function openSettings(page: Page) {
  await primeSettingsState(page);
  await page.goto("/settings", { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("networkidle", { timeout: 8_000 }).catch(() => {});
  await expect(page.getByRole("dialog", { name: /Settings/i })).toBeVisible();
}

test.describe("Settings provider configuration smoke", () => {
  test("renders model provider catalog while backend generation paths are blocked", async ({ page }) => {
    const violations = await installSettingsUiGuards(page);
    await openSettings(page);

    await page.getByRole("button", { name: /Providers/i }).click();

    await expect(page.getByText("Provider API keys")).toBeVisible();
    await expect(page.getByText("Model route catalog")).toBeVisible();

    for (const capability of [
      "Text reasoning",
      "Image generation",
      "Video generation",
      "Voice and TTS",
      "Music and audio",
    ]) {
      await expect(page.getByRole("heading", { name: capability })).toBeVisible();
    }

    await expect(page.locator("#settings-provider-key-DEEPSEEK_API_KEY")).toHaveAttribute("type", "password");
    await expect(page.locator("#settings-provider-key-POYO_API_KEY")).toHaveAttribute("type", "password");
    await expect(page.locator("#settings-provider-key-SILICONFLOW_API_KEY")).toHaveAttribute("type", "password");
    await expect(page.getByText("POYO_VIDEO_MODEL: seedance-2")).toBeVisible();
    await expect(page.getByText("POYO_IMAGE_MODEL: gpt-image-2")).toBeVisible();

    expect(violations, "settings page must not call token-consuming endpoints").toEqual([]);
  });

  test("masks saved access key display and stores provider keys only after explicit save", async ({ page }) => {
    const violations = await installSettingsUiGuards(page);
    await openSettings(page);

    const accessKey = "tenant-secret-abcdef123456";
    await page.locator("#settings-api-key").fill(accessKey);

    const visibleBeforeSave = await page.locator("body").innerText();
    expect(visibleBeforeSave).not.toContain(accessKey);
    await expect(page.locator("p").filter({ hasText: /tena.*456/ }).first()).toBeVisible();

    await page.getByRole("button", { name: /Providers/i }).click();
    await page.locator("#settings-provider-key-POYO_API_KEY").fill("poyo-e2e-session-key");
    await expect(page.locator("#settings-provider-key-POYO_API_KEY")).toHaveAttribute("type", "password");

    const visibleAfterProviderFill = await page.locator("body").innerText();
    expect(visibleAfterProviderFill).not.toContain("poyo-e2e-session-key");

    await page.getByRole("button", { name: /Save settings/i }).click();
    await expect(page.getByRole("dialog", { name: /Settings/i })).toBeHidden();

    const saved = await page.evaluate(() => ({
      apiKey: localStorage.getItem("ai_video_api_key"),
      providerConfig: JSON.parse(localStorage.getItem("ai_video_provider_config") || "{}") as {
        apiKeys?: Record<string, string>;
      },
    }));
    expect(saved.apiKey).toBe(accessKey);
    expect(saved.providerConfig.apiKeys?.POYO_API_KEY).toBe("poyo-e2e-session-key");
    expect(violations, "saving settings must not call token-consuming endpoints").toEqual([]);
  });
});
