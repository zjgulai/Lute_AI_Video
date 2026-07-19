/**
 * P4-1 — Production user-journey spec.
 * Backend API contract used: POST /api/fast/submit, GET /api/fast/status/{id}, GET /api/portfolio/.
 * Run: PLAYWRIGHT_PROD_URL=https://video.lute-tlz-dddd.top npm run e2e:prod -- user-journey
 */
import { test, expect, type APIRequestContext } from "@playwright/test";
import {
  expectOkJsonWith429Retry,
  productionApiHeaders,
  productionSubmitHeaders,
} from "./helpers";

type PortfolioResponse = {
  files?: unknown[];
};

async function expectOkJson(request: APIRequestContext, path: string) {
  return expectOkJsonWith429Retry(request, path, { headers: productionApiHeaders() });
}

test.describe("P4-1 — End-to-end user journey", () => {
  test.describe.configure({ mode: "serial" });

  test("step 1: home page renders without blocking errors", async ({ page }) => {
    const pageErrors: string[] = [];
    page.on("pageerror", (e) => pageErrors.push(e.message));

    const resp = await page.goto("/", { waitUntil: "domcontentloaded" });
    expect(resp?.status()).toBeLessThan(400);
    await expect(page.locator("body")).toBeVisible();
    expect(pageErrors).toEqual([]);
  });

  test("step 2: settings page reachable (handles session redirect)", async ({ page }) => {
    const resp = await page.goto("/settings", { waitUntil: "domcontentloaded" });
    expect(resp?.status()).toBeLessThan(400);
    await page.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => { void 0; });
    await expect(page.locator("body")).toBeVisible();
  });

  test("step 3: fast mode page reachable (handles session redirect)", async ({ page }) => {
    const resp = await page.goto("/fast", { waitUntil: "domcontentloaded" });
    expect(resp?.status()).toBeLessThan(400);
    await page.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => { void 0; });
    await expect(page.locator("body")).toBeVisible();
  });

  test("step 4: backend submits async task and returns task_id < 5s @token-smoke", async ({ request }) => {
    const start = Date.now();
    const resp = await request.post("/api/fast/submit", {
      headers: productionSubmitHeaders("user-journey-submit", {
        "Content-Type": "application/json",
      }),
      data: { user_prompt: "P4-1 user-journey probe", duration: 15 },
    });
    const elapsed = Date.now() - start;

    expect(resp.status(), "fast/submit must return 200").toBe(200);
    expect(elapsed, "submit must be non-blocking (<5s)").toBeLessThan(5_000);

    const body = await resp.json();
    expect(body).toHaveProperty("task_id");
    expect(body.task_id).toMatch(/^fast_\d+_[a-f0-9]+/);
    expect(body.status).toBe("queued");
  });

  test("step 5: status endpoint reflects progress @token-smoke", async ({ request }) => {
    const submit = await request.post("/api/fast/submit", {
      headers: productionSubmitHeaders("user-journey-status", {
        "Content-Type": "application/json",
      }),
      data: { user_prompt: "P4-1 status probe", duration: 15 },
    });
    expect(submit.status()).toBe(200);
    const { task_id } = await submit.json();

    await new Promise((r) => setTimeout(r, 3_000));

    const status = await request.get(`/api/fast/status/${task_id}`, {
      headers: productionApiHeaders(),
    });
    expect(status.status()).toBe(200);
    const body = await status.json();
    expect(body.task_id).toBe(task_id);
    expect(["queued", "running", "done", "failed"]).toContain(body.status);
    expect(typeof body.elapsed_sec).toBe("number");
  });

  test("step 6: /works gallery exposes portfolio listing", async ({ page, request }) => {
    const portfolio = await expectOkJson(request, "/api/portfolio/?limit=10") as PortfolioResponse;
    const files = portfolio.files;
    if (!Array.isArray(files)) {
      throw new Error("portfolio.files must be an array");
    }
    expect(files.length, "portfolio must have files").toBeGreaterThan(0);

    await page.goto("/works", { waitUntil: "domcontentloaded" });
    await expect(page.locator("body")).toBeVisible();
    await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => { void 0; });
  });

  test("step 7: unknown task_id returns 404 (negative path)", async ({ request }) => {
    const r = await request.get("/api/fast/status/fake_task_does_not_exist_xyz", {
      headers: productionApiHeaders(),
    });
    expect(r.status()).toBe(404);
  });
});
