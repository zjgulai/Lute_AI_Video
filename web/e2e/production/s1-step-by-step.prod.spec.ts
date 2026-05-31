import { test, expect } from "@playwright/test";

const API_KEY = process.env.PLAYWRIGHT_API_KEY || "ai_video_demo_2026";

test.describe("Production smoke — S1 step_by_step", () => {
  test("POST /api/scenario/s1/start returns label @token-smoke", async ({ request }) => {
    const r = await request.post("/api/scenario/s1/start", {
      headers: { "X-API-Key": API_KEY, "Content-Type": "application/json" },
      data: {
        product_catalog: {
          products: [
            {
              name: "test apple",
              usps: [{ text: "fresh", priority: "P0" }],
              category: "food",
              target_audience: "test",
            },
          ],
        },
        brand_guidelines: { brand_name: "TestBrand" },
        target_platforms: ["tiktok"],
        video_duration: 15,
        mode: "step_by_step",
      },
    });
    expect(r.status()).toBe(200);
    const body = await r.json();
    expect(body.label).toMatch(/^s1_\d+_[a-f0-9]+$/);
    expect(body.status).toBe("initialized");
    expect(body.mode).toBe("step_by_step");
  });

  test("POST /api/scenario/s1/step/strategy completes successfully (no missing-name error) @token-smoke", async ({ request }) => {
    const initR = await request.post("/api/scenario/s1/start", {
      headers: { "X-API-Key": API_KEY, "Content-Type": "application/json" },
      data: {
        product_catalog: {
          products: [
            {
              name: "blue ocean wave",
              usps: [{ text: "calm", priority: "P0" }],
              category: "lifestyle",
              target_audience: "viewers",
            },
          ],
        },
        target_platforms: ["tiktok"],
        video_duration: 15,
        mode: "step_by_step",
      },
    });
    expect(initR.status()).toBe(200);
    const label = (await initR.json()).label;

    const stepR = await request.post("/api/scenario/s1/step/strategy", {
      headers: { "X-API-Key": API_KEY, "Content-Type": "application/json" },
      data: { label },
      timeout: 30_000,
    });
    expect(stepR.status()).toBe(200);
    const state = await stepR.json();

    const strategyStep = state.steps?.strategy;
    expect(strategyStep).toBeDefined();
    expect(strategyStep.status).toBe("done");

    const errors = state.errors || [];
    const missingNameErr = errors.find((e: string) =>
      typeof e === "string" && e.includes("missing product_name/name"),
    );
    expect(
      missingNameErr,
      `INTEGRATION-3 regression: validator rejected nested products[0].name shape`,
    ).toBeUndefined();
  });

  test("/s1 page renders without backend coupling", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("console", (msg) => {
      if (msg.type() === "error") errors.push(msg.text());
    });

    await page.goto("/s1");
    await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => {});

    const url = page.url();
    if (url.includes("session_expired")) {
      test.skip(true, "S1 page requires session — skipping UI test");
      return;
    }

    await expect(page.locator("body")).toBeVisible();
    const html = await page.content();
    expect(html.length).toBeGreaterThan(1000);
  });
});
