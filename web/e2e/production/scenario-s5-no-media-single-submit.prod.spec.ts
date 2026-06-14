import { test, expect } from "@playwright/test";
import { productionApiHeaders } from "./helpers";

const maxSubmitCount = Number(process.env.PLAYWRIGHT_MAX_SUBMIT_COUNT ?? "1");
const providerMaxRetries = Number(process.env.PLAYWRIGHT_PROVIDER_MAX_RETRIES ?? "0");
const artifactDisposition = process.env.PLAYWRIGHT_ARTIFACT_DISPOSITION ?? "pending_review";

test.describe("Production smoke — S5 no-media single-submit token smoke", () => {
  test.setTimeout(120_000);

  test("single S5 no-media submit returns brand vlog result without media synthesis @token-smoke", async ({ request }) => {
    expect(maxSubmitCount, "L4C-8 must be capped to a single submit").toBe(1);
    expect(providerMaxRetries, "L4C-8 provider/backend retries must be disabled").toBe(0);
    expect(["pending_review", "quarantine"]).toContain(artifactDisposition);

    let submitCount = 0;
    submitCount += 1;
    expect(submitCount, "submit count exceeded authorized max_submit_count").toBeLessThanOrEqual(maxSubmitCount);

    const response = await request.post("/api/scenario/s5", {
      headers: productionApiHeaders({ "Content-Type": "application/json" }),
      timeout: 120_000,
      data: {
        brand_id: "momcozy",
        product_sku: {
          name: "Momcozy UV Sterilizer",
          shortName: "UV Sterilizer",
          tags: ["baby feeding appliance", "daily hygiene", "countertop routine"],
          views: [
            { label: "front view", title: "Front View", usage_note: "Hero product view" },
            { label: "detail view", title: "Detail View", usage_note: "Control panel close-up" },
            { label: "countertop view", title: "Countertop View", usage_note: "Kitchen counter placement" },
          ],
        },
        scene_id: "kitchen",
        selected_models: [],
        story_description: "A calm 15-second countertop routine for new parents.",
        video_duration: 15,
        enable_media_synthesis: false,
        commercial_injection_plan: null,
      },
    });

    if ([401, 403, 422, 429].includes(response.status())) {
      throw new Error(`L4C-8 stop-loss status from S5 submit: ${response.status()} ${await response.text()}`);
    }

    expect(response.status(), "single S5 no-media submit should complete").toBe(200);
    const body = await response.json();

    expect(body.success).toBe(true);
    expect(body.scenario).toBe("brand_vlog");
    expect(body.video_duration).toBe(15);
    expect(Array.isArray(body.scripts)).toBe(true);
    expect(body.scripts.length).toBeGreaterThan(0);
    expect(body.errors ?? []).toEqual([]);
    expect(body.media_synthesis_errors ?? []).toEqual([]);
    expect(body.video_prompts ?? []).toEqual([]);
    expect(body.thumbnail_sets ?? []).toEqual([]);
    expect(body.seedance_clips ?? []).toEqual([]);
    expect(body.clip_paths ?? []).toEqual([]);
    expect(body.audio_paths ?? []).toEqual([]);
    expect(body.final_video_path ?? "").toBe("");
    expect(body.render_json_path ?? "").toBe("");
    expect(submitCount).toBe(1);
  });
});
