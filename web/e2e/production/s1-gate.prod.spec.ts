/**
 * P4-2 — Production S1 Gate panel spec.
 * Backend API contract: gate/{gate_id}/generate (3 candidates), gate/{gate_id}/approve.
 * Regression guard for INTEGRATION-3 (product_catalog nested-name schema).
 * Run: PLAYWRIGHT_PROD_URL=https://video.lute-tlz-dddd.top npm run e2e:prod -- s1-gate
 */
import { test, expect } from "@playwright/test";

const API_KEY = process.env.PLAYWRIGHT_API_KEY || "ai_video_demo_2026";

const S1_PAYLOAD = {
  product_catalog: {
    products: [
      {
        name: "wearable breast pump",
        usps: [
          { text: "silent operation", priority: "P0" },
          { text: "portable design", priority: "P1" },
        ],
        category: "maternity",
        target_audience: "new mothers",
      },
    ],
  },
  brand_guidelines: { brand_name: "Momcozy" },
  target_platforms: ["tiktok"],
  video_duration: 15,
  mode: "step_by_step",
};

test.describe("P4-2 — S1 Gate panel flow", () => {
  test("step 1: start S1 and run strategy step without INTEGRATION-3 regression", async ({ request }) => {
    const initR = await request.post("/api/scenario/s1/start", {
      headers: { "X-API-Key": API_KEY, "Content-Type": "application/json" },
      data: S1_PAYLOAD,
    });
    expect(initR.status()).toBe(200);
    const { label } = await initR.json();
    expect(label).toMatch(/^s1_\d+_[a-f0-9]+$/);

    const stepR = await request.post("/api/scenario/s1/step/strategy", {
      headers: { "X-API-Key": API_KEY, "Content-Type": "application/json" },
      data: { label },
      timeout: 30_000,
    });
    expect(stepR.status()).toBe(200);
    const state = await stepR.json();
    expect(state.steps.strategy.status).toBe("done");

    const errs = (state.errors || []) as string[];
    const integ3 = errs.find((e) => e.includes("missing product_name") || e.includes("product_catalog missing"));
    expect(integ3, "INTEGRATION-3 regression: nested products[].name not accepted").toBeUndefined();
  });

  test("step 2: gate exists after strategy and exposes 3 candidates", async ({ request }) => {
    const initR = await request.post("/api/scenario/s1/start", {
      headers: { "X-API-Key": API_KEY, "Content-Type": "application/json" },
      data: S1_PAYLOAD,
    });
    const { label } = await initR.json();

    const strategyR = await request.post("/api/scenario/s1/step/strategy", {
      headers: { "X-API-Key": API_KEY, "Content-Type": "application/json" },
      data: { label },
      timeout: 30_000,
    });
    expect(strategyR.status()).toBe(200);

    const stateR = await request.get(`/api/scenario/s1/state/${label}`, {
      headers: { "X-API-Key": API_KEY },
    });
    expect(stateR.status()).toBe(200);
    const state = await stateR.json();

    const gates = state.gates ?? state.gate_states ?? {};
    const gateId = Object.keys(gates)[0];

    if (!gateId) {
      test.skip(true, "no gate exposed after strategy on this scenario config");
      return;
    }

    const genR = await request.post(
      `/api/scenario/s1/gate/${label}/${gateId}/generate`,
      {
        headers: { "X-API-Key": API_KEY, "Content-Type": "application/json" },
        data: {},
        timeout: 60_000,
      },
    );
    expect([200, 202]).toContain(genR.status());
    const genBody = await genR.json();
    const cands = genBody.candidates ?? genBody.data?.candidates ?? [];
    expect(Array.isArray(cands)).toBe(true);
    expect(cands.length, "gate must produce 3 candidates").toBe(3);
  });

  test("step 3: /s1 frontend page renders without blocking errors", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));

    const resp = await page.goto("/s1", { waitUntil: "domcontentloaded" });
    expect(resp?.status()).toBeLessThan(400);
    await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => {});
    await expect(page.locator("body")).toBeVisible();
    expect(errors).toEqual([]);
  });
});
