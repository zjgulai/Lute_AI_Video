import { expect, test, type Page, type Route } from "@playwright/test";

const GENERATION_ENDPOINT_PATTERNS = [
  /\/fast\/(?:generate|submit|status)/,
  /\/scenario\/[^/]+(?:$|\/(?:submit|start|step|resume|regenerate|gate))/,
  /\/pipeline\/(?:start|[^/]+\/(?:review|distribution|output))/,
  /\/distribution\/publish/,
  /\/publish\//,
  /\/api\/upload/,
];

const ROUTES_TO_CAPTURE = [
  { name: "home", path: "/" },
  { name: "s1-expert", path: "/s1?mode=expert" },
  { name: "works", path: "/works" },
  { name: "library", path: "/library" },
] as const;

function isBackendUrl(url: string): boolean {
  return url.includes("localhost:8001") || /\/api(?:\/|$)/.test(new URL(url).pathname);
}

function matchesGenerationEndpoint(url: string): boolean {
  return GENERATION_ENDPOINT_PATTERNS.some((pattern) => pattern.test(new URL(url).pathname));
}

async function fulfillJson(route: Route, body: unknown) {
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function installUiOnlyGuards(page: Page): Promise<string[]> {
  const violations: string[] = [];

  await page.route("**/*", async (route) => {
    const request = route.request();
    const url = request.url();
    const method = request.method().toUpperCase();
    const parsed = new URL(url);
    const pathname = parsed.pathname;

    if (matchesGenerationEndpoint(url) || !["GET", "HEAD", "OPTIONS"].includes(method)) {
      violations.push(`${method} ${pathname}`);
      await route.fulfill({
        status: 451,
        contentType: "application/json",
        body: JSON.stringify({ error: "UI-only Playwright run blocked a token-consuming request" }),
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
        scraped_at: "2026-05-31T00:00:00Z",
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
      body: JSON.stringify({ error: "UI-only mock does not serve this backend route" }),
    });
  });

  return violations;
}

async function primeUiState(page: Page) {
  await page.addInitScript(() => {
    localStorage.clear();
    localStorage.setItem("ai_video_api_key", "ui_only_fake_key");
    localStorage.setItem("ai_video_demo_mode", "true");
    localStorage.setItem("app-locale", "zh");
    localStorage.setItem("ai-video-app-store", JSON.stringify({
      state: {
        mode: "expert",
        pipelineMode: "step_by_step",
        videoDuration: 30,
      },
      version: 1,
    }));
  });
}

async function openApp(page: Page, path: string) {
  await primeUiState(page);
  await page.goto(path, { waitUntil: "domcontentloaded" });

  const splashMarker = page.getByText("Evolving for Mom and Cozy");
  if (await splashMarker.isVisible().catch(() => false)) {
    await page.getByRole("button", { name: /开始创作|Get Started/i }).evaluate((node) => {
      (node as HTMLButtonElement).click();
    });
    await expect(splashMarker).toBeHidden({ timeout: 5_000 });
  }

  const nav = page.locator("nav").first();
  await nav.waitFor({ state: "visible", timeout: 2_000 }).catch(() => { /* fallback to explicit splash dismissal */ });
  if (!await nav.isVisible().catch(() => false)) {
    const enter = page.getByRole("button", { name: /开始创作|Get Started|进入|Enter/i }).first();
    if (await enter.isVisible().catch(() => false)) {
      await enter.evaluate((node) => (node as HTMLButtonElement).click());
    }
    await nav.waitFor({ state: "visible", timeout: 10_000 });
  }

  await page.addStyleTag({
    content: `
      *, *::before, *::after {
        animation-delay: 0s !important;
        animation-duration: 0s !important;
        transition-delay: 0s !important;
        transition-duration: 0s !important;
        caret-color: transparent !important;
      }
      video { visibility: hidden !important; }
    `,
  });

  await page.waitForLoadState("networkidle", { timeout: 8_000 }).catch(() => { /* UI-only pages may keep probes alive. */ });
  await expect(page.locator("body")).toBeVisible();
  await expect(nav).toBeVisible();
}

test.describe("P1-8 UI-only visual baselines", () => {
  for (const route of ROUTES_TO_CAPTURE) {
    test(`${route.name} has stable ${route.path} layout`, async ({ page }, testInfo) => {
      const violations = await installUiOnlyGuards(page);
      await openApp(page, route.path);

      await expect(page).toHaveScreenshot(`${testInfo.project.name}-${route.name}.png`, {
        animations: "disabled",
        caret: "hide",
        maxDiffPixelRatio: 0.02,
      });
      expect(violations, "token-consuming or mutating requests must stay blocked").toEqual([]);
    });
  }
});

test.describe("P1-8 UI-only interaction guards", () => {
  test("QuickTemplate supports keyboard open, navigation and Escape restore", async ({ page }) => {
    const violations = await installUiOnlyGuards(page);
    await openApp(page, "/");

    const trigger = page.getByRole("button", { name: /快捷模板|Quick Templates/i });
    await expect(trigger).toBeVisible();
    await trigger.click();

    const menu = page.getByRole("menu", { name: /快捷模板|Quick Templates/i });
    await expect(menu).toBeVisible();

    const firstItem = page.getByRole("menuitem").first();
    await expect(firstItem).toBeFocused();
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("Home");
    await expect(firstItem).toBeFocused();

    await page.keyboard.press("Escape");
    await expect(menu).toBeHidden();
    await expect(trigger).toBeFocused();
    expect(violations, "opening templates must not call generation endpoints").toEqual([]);
  });
});
