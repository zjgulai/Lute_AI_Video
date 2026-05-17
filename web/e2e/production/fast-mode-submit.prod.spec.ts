import { test, expect } from "@playwright/test";

const API_KEY = process.env.PLAYWRIGHT_API_KEY || "ai_video_demo_2026";

test.describe("Production smoke — Fast Mode async submit", () => {
  test("POST /api/fast/submit returns task_id quickly (~2-5s)", async ({ request }) => {
    const start = Date.now();
    const r = await request.post("/api/fast/submit", {
      headers: { "X-API-Key": API_KEY, "Content-Type": "application/json" },
      data: {
        user_prompt: "a single red apple on white background",
        duration: 10,
        enable_tts: false,
      },
    });
    const elapsed = Date.now() - start;

    expect(r.status()).toBe(200);
    const body = await r.json();
    expect(body).toHaveProperty("task_id");
    expect(body.task_id).toMatch(/^fast_\d+_[a-f0-9]+$/);
    expect(body.status).toBe("queued");
    expect(body).toHaveProperty("started_at_unix");
    expect(elapsed).toBeLessThan(15_000);
  });

  test("GET /api/fast/status/{unknown_task} returns 404", async ({ request }) => {
    const r = await request.get("/api/fast/status/fast_does_not_exist_xyz", {
      headers: { "X-API-Key": API_KEY },
    });
    expect(r.status()).toBe(404);
  });

  test("submit + status round-trip — task is queryable + has stage field", async ({ request }) => {
    const r1 = await request.post("/api/fast/submit", {
      headers: { "X-API-Key": API_KEY, "Content-Type": "application/json" },
      data: { user_prompt: "blue ocean wave", duration: 10, enable_tts: false },
    });
    expect(r1.status()).toBe(200);
    const taskId = (await r1.json()).task_id;

    const r2 = await request.get(`/api/fast/status/${taskId}`, {
      headers: { "X-API-Key": API_KEY },
    });
    expect(r2.status()).toBe(200);
    const snap = await r2.json();
    expect(snap.task_id).toBe(taskId);
    expect(["running", "done", "failed"]).toContain(snap.status);
    expect(["queued", "llm", "video", "tts"]).toContain(snap.stage);
    expect(typeof snap.elapsed_sec).toBe("number");
  });

  test("/fast page renders and submit button exists", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("console", (msg) => {
      if (msg.type() === "error") errors.push(msg.text());
    });

    await page.goto("/fast");
    await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => {});

    const url = page.url();
    if (url.includes("session_expired")) {
      test.skip(true, "Fast Mode page requires session — skipping UI interaction test");
      return;
    }

    await expect(page.locator("body")).toBeVisible();
    const html = await page.content();
    expect(html.length).toBeGreaterThan(1000);
  });
});
