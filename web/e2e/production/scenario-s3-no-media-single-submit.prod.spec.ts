import { test, expect } from "@playwright/test";
import { productionApiHeaders } from "./helpers";

const maxSubmitCount = Number(process.env.PLAYWRIGHT_MAX_SUBMIT_COUNT ?? "1");
const providerMaxRetries = Number(process.env.PLAYWRIGHT_PROVIDER_MAX_RETRIES ?? "0");
const artifactDisposition = process.env.PLAYWRIGHT_ARTIFACT_DISPOSITION ?? "pending_review";

test.describe("Production smoke — S3 no-media single-submit token smoke", () => {
  test("single S3 no-media submit returns influencer remix result without media synthesis @token-smoke", async ({ request }) => {
    expect(maxSubmitCount, "L4C-6 must be capped to a single submit").toBe(1);
    expect(providerMaxRetries, "L4C-6 provider/backend retries must be disabled").toBe(0);
    expect(["pending_review", "quarantine"]).toContain(artifactDisposition);

    let submitCount = 0;
    submitCount += 1;
    expect(submitCount, "submit count exceeded authorized max_submit_count").toBeLessThanOrEqual(maxSubmitCount);

    const response = await request.post("/api/scenario/s3", {
      headers: productionApiHeaders({ "Content-Type": "application/json" }),
      timeout: 90_000,
      data: {
        video_url: "https://www.tiktok.com/@momcozy/video/1000000000",
        product: {
          name: "Momcozy UV Sterilizer",
          brand_name: "Momcozy",
          category: "baby feeding appliance",
          usps: [
            "helps keep feeding accessories clean",
            "quiet countertop routine",
            "easy daily use for new parents",
          ],
          target_audience: "new parents",
        },
        influencer_name: "Test Influencer",
        target_platforms: ["tiktok"],
        video_duration: 15,
        enable_media_synthesis: false,
        commercial_injection_plan: null,
      },
    });

    if ([401, 403, 422, 429].includes(response.status())) {
      throw new Error(`L4C-6 stop-loss status from S3 submit: ${response.status()} ${await response.text()}`);
    }

    expect(response.status(), "single S3 no-media submit should complete").toBe(200);
    const body = await response.json();

    expect(body.success).toBe(true);
    expect(body.video_analysis).toBeTruthy();
    expect(body.remix_script).toBeTruthy();
    expect(body.identity_card).toBeTruthy();
    expect(body.video_prompts ?? []).toEqual([]);
    expect(body.thumbnail_sets ?? []).toEqual([]);
    expect(body.thumbnail_prompts ?? []).toEqual([]);
    expect(body.storyboard_with_keyframes ?? null).toBeNull();
    expect(body.errors ?? []).toEqual([]);
    expect(body.media_synthesis_errors ?? []).toEqual([]);
    expect(body.clip_paths ?? []).toEqual([]);
    expect(body.audio_paths ?? []).toEqual([]);
    expect(body.thumbnail_image_paths ?? []).toEqual([]);
    expect(body.final_video_path ?? "").toBe("");
    expect(body.render_json_path ?? "").toBe("");
    expect(submitCount).toBe(1);
  });
});
