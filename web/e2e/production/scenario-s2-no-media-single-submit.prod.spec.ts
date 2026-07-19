import { test, expect } from "@playwright/test";
import { productionApiHeaders } from "./helpers";

const maxSubmitCount = Number(process.env.PLAYWRIGHT_MAX_SUBMIT_COUNT ?? "1");
const providerMaxRetries = Number(process.env.PLAYWRIGHT_PROVIDER_MAX_RETRIES ?? "0");
const artifactDisposition = process.env.PLAYWRIGHT_ARTIFACT_DISPOSITION ?? "pending_review";

test.describe("Production smoke — S2 no-media single-submit token smoke", () => {
  test("single S2 no-media submit returns brand campaign result without media synthesis @token-smoke", async ({ request }) => {
    expect(maxSubmitCount, "L4C-2 must be capped to a single submit").toBe(1);
    expect(providerMaxRetries, "L4C-2 provider/backend retries must be disabled").toBe(0);
    expect(["pending_review", "quarantine"]).toContain(artifactDisposition);

    let submitCount = 0;
    submitCount += 1;
    expect(submitCount, "submit count exceeded authorized max_submit_count").toBeLessThanOrEqual(maxSubmitCount);

    const response = await request.post("/api/scenario/s2", {
      headers: productionApiHeaders({ "Content-Type": "application/json" }),
      timeout: 90_000,
      data: {
        brand_package: {
          brand_name: "Momcozy",
          values: ["safety", "comfort", "parent trust"],
          voice_guidelines: "warm, practical, no exaggeration",
        },
        target_platforms: ["tiktok"],
        video_duration: 15,
        enable_media_synthesis: false,
        artifact_disposition: artifactDisposition,
        provider_max_retries: providerMaxRetries,
        commercial_injection_plan: null,
      },
    });

    if ([401, 403, 422, 429].includes(response.status())) {
      throw new Error(`L4C-2 stop-loss status from S2 submit: ${response.status()} ${await response.text()}`);
    }

    expect(response.status(), "single S2 no-media submit should complete").toBe(200);
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
    expect(body.scenario).toBe("brand_campaign");
    expect(body.brand_name).toBe("Momcozy");
    expect(body.video_duration).toBe(15);
    expect(Array.isArray(body.briefs)).toBe(true);
    expect(Array.isArray(body.scripts)).toBe(true);
    expect(body.errors ?? []).toEqual([]);
    expect(body.media_synthesis_errors ?? []).toEqual([]);
    expect(Array.isArray(body.keyframe_images)).toBe(true);
    expect(body.keyframe_images).toHaveLength(0);
    expect(body.clip_paths ?? []).toEqual([]);
    expect(body.audio_paths ?? []).toEqual([]);
    expect(body.thumbnail_image_paths ?? []).toEqual([]);
    expect(body.final_video_path ?? "").toBe("");
    expect(submitCount).toBe(1);
  });
});
