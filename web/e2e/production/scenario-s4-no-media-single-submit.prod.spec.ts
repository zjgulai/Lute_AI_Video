import { test, expect } from "@playwright/test";
import { productionApiHeaders } from "./helpers";

const maxSubmitCount = Number(process.env.PLAYWRIGHT_MAX_SUBMIT_COUNT ?? "1");
const providerMaxRetries = Number(process.env.PLAYWRIGHT_PROVIDER_MAX_RETRIES ?? "0");
const artifactDisposition = process.env.PLAYWRIGHT_ARTIFACT_DISPOSITION ?? "pending_review";

test.describe("Production smoke — S4 no-media single-submit token smoke", () => {
  test("single S4 no-media submit returns live shoot result without media synthesis @token-smoke", async ({ request }) => {
    expect(maxSubmitCount, "L4C-7 must be capped to a single submit").toBe(1);
    expect(providerMaxRetries, "L4C-7 provider/backend retries must be disabled").toBe(0);
    expect(["pending_review", "quarantine"]).toContain(artifactDisposition);

    let submitCount = 0;
    submitCount += 1;
    expect(submitCount, "submit count exceeded authorized max_submit_count").toBeLessThanOrEqual(maxSubmitCount);

    const response = await request.post("/api/scenario/s4", {
      headers: productionApiHeaders({ "Content-Type": "application/json" }),
      timeout: 90_000,
      data: {
        product_info: {
          name: "Momcozy UV Sterilizer",
          brand_name: "Momcozy",
          category: "baby feeding appliance",
          usps: [
            "helps keep feeding accessories clean",
            "quiet countertop routine",
            "easy daily use for new parents",
          ],
          usage_scenario: "kitchen counter daily hygiene",
        },
        footage_assets: [],
        target_platforms: ["tiktok"],
        topic: "15-second practical product routine",
        video_duration: 15,
        enable_media_synthesis: false,
        artifact_disposition: artifactDisposition,
        provider_max_retries: providerMaxRetries,
        commercial_injection_plan: null,
      },
    });

    if ([401, 403, 422, 429].includes(response.status())) {
      throw new Error(`L4C-7 stop-loss status from S4 submit: ${response.status()} ${await response.text()}`);
    }

    expect(response.status(), "single S4 no-media submit should complete").toBe(200);
    const body = await response.json();

    expect(body.status).toBe("completed_bounded");
    expect(body.lifecycle_status).toBe("completed_bounded");
    expect(body.completion_kind).toBe("no_media");
    expect(body.request_succeeded).toBe(true);
    expect(body.success).toBe(false);
    expect(body.full_media_success).toBe(false);
    expect(body.pipeline_complete).toBe(false);
    expect(body.publish_allowed).toBe(false);
    expect(body.delivery_accepted).toBe(false);
    expect(body.scenario).toBe("s4_live_shoot");
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
