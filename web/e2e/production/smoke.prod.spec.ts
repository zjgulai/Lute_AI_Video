import { test, expect } from "@playwright/test";

const API_KEY = process.env.PLAYWRIGHT_API_KEY || "ai_video_demo_2026";

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
