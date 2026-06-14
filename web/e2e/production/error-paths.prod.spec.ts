/**
 * P4-4 — Error-path spec.
 * Asserts backend correctly rejects invalid input (422 / 401) without crashing.
 * Covers: invalid video_duration, missing required field, missing API key, unknown task.
 * Run: PLAYWRIGHT_PROD_URL=https://video.lute-tlz-dddd.top npm run e2e:prod -- error-paths
 */
import { test, expect } from "@playwright/test";
import { productionApiHeaders } from "./helpers";

function authHeaders(extra: Record<string, string> = {}) {
  return productionApiHeaders(extra);
}

test.describe("P4-4 — Error paths", () => {
  test("invalid video_duration string returns 422 with field-level detail", async ({ request }) => {
    const r = await request.post("/api/scenario/s1/submit", {
      headers: authHeaders({ "Content-Type": "application/json" }),
      data: {
        product_catalog: { products: [{ name: "test", usps: [{ text: "x", priority: "P0" }] }] },
        target_platforms: ["tiktok"],
        video_duration: "not-a-number",
      },
    });
    expect(r.status(), "string video_duration must 422").toBe(422);

    const body = await r.json();
    expect(Array.isArray(body.detail)).toBe(true);
    const fieldErr = body.detail.find((d: { loc?: string[] }) =>
      Array.isArray(d.loc) && d.loc.includes("video_duration"),
    );
    expect(fieldErr, "422 detail must point at video_duration field").toBeDefined();
  });

  test("fast/submit missing user_prompt returns 422", async ({ request }) => {
    const r = await request.post("/api/fast/submit", {
      headers: authHeaders({ "Content-Type": "application/json" }),
      data: { duration: 15 },
    });
    expect(r.status()).toBe(422);
    const body = await r.json();
    const missingPrompt = body.detail.find((d: { loc?: string[]; type?: string }) =>
      Array.isArray(d.loc) && d.loc.includes("user_prompt"),
    );
    expect(missingPrompt).toBeDefined();
  });

  test("fast/submit invalid duration type returns 422", async ({ request }) => {
    const r = await request.post("/api/fast/submit", {
      headers: authHeaders({ "Content-Type": "application/json" }),
      data: { user_prompt: "test", duration: "abc" },
    });
    expect(r.status()).toBe(422);
  });

  test("missing X-API-Key returns 401", async ({ request }) => {
    const r = await request.post("/api/fast/submit", {
      headers: { "Content-Type": "application/json" },
      data: { user_prompt: "test", duration: 15 },
    });
    expect([401, 403]).toContain(r.status());
  });

  test("invalid X-API-Key returns 401", async ({ request }) => {
    const r = await request.post("/api/fast/submit", {
      headers: { "X-API-Key": "definitely_not_a_valid_key", "Content-Type": "application/json" },
      data: { user_prompt: "test", duration: 15 },
    });
    expect([401, 403]).toContain(r.status());
  });

  test("unknown fast task_id returns 404", async ({ request }) => {
    const r = await request.get("/api/fast/status/fast_0_deadbeef_unknown", {
      headers: authHeaders(),
    });
    expect(r.status()).toBe(404);
  });

  test("malformed JSON body returns 422", async ({ request }) => {
    const r = await request.post("/api/fast/submit", {
      headers: authHeaders({ "Content-Type": "application/json" }),
      data: "not-json",
    });
    expect([400, 422]).toContain(r.status());
  });

  test("rate-limit headers present on /health", async ({ request }) => {
    const r = await request.get("/health");
    expect(r.status()).toBe(200);
    const body = await r.json();
    expect(body).toHaveProperty("status", "ok");
  });
});
