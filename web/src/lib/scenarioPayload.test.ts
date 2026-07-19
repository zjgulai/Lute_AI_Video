import { describe, expect, it } from "vitest";

import {
  buildS1EditedStateUpdate,
  buildScenarioAutoSubmitPayload,
  withExplicitMediaGenerationIntent,
} from "./scenarioPayload";

describe("buildScenarioAutoSubmitPayload", () => {
  it.each([
    "product_direct",
    "brand_campaign",
    "influencer_remix",
    "live_shoot_to_video",
    "brand_vlog",
  ])("defaults %s submissions to no-media pending-review retry-zero", (contentScenario) => {
    const payload = buildScenarioAutoSubmitPayload({
      content_scenario: contentScenario,
      product_catalog: { name: "Fixture" },
    });

    expect(payload.enable_media_synthesis).toBe(false);
    expect(payload.artifact_disposition).toBe("pending_review");
    expect(payload.provider_max_retries).toBe(0);
  });

  it("preserves exact false and zero values", () => {
    const payload = buildScenarioAutoSubmitPayload({
      content_scenario: "product_direct",
      product_catalog: { name: "Fixture" },
      enable_media_synthesis: false,
      artifact_disposition: "pending_review",
      provider_max_retries: 0,
    });

    expect(payload).toMatchObject({
      enable_media_synthesis: false,
      artifact_disposition: "pending_review",
      provider_max_retries: 0,
    });
  });

  it("adds provider-on intent only for an explicit user generation action", () => {
    const payload = withExplicitMediaGenerationIntent({ user_prompt: "make a video" });

    expect(payload).toEqual({
      user_prompt: "make a video",
      enable_media_synthesis: true,
      artifact_disposition: "pending_review",
      provider_max_retries: 0,
    });
  });

  it("preserves S2 campaign fields in a brand_package object", () => {
    const payload = buildScenarioAutoSubmitPayload({
      content_scenario: "brand_campaign",
      brand_package: "Momcozy",
      campaign_theme: "Sleep better while pumping",
      key_message: "Hands-free confidence for new moms",
      target_audience: "Postpartum moms",
      brand_guidelines: {
        brand_name: "Momcozy",
        tone_of_voice: { keywords: ["warm", "supportive"] },
        visual_identity: "soft home lighting",
      },
      target_platforms: ["tiktok"],
      video_duration: 45,
    });

    expect(payload).toMatchObject({
      brand_package: {
        brand_name: "Momcozy",
        campaign_theme: "Sleep better while pumping",
        key_message: "Hands-free confidence for new moms",
        target_audience: "Postpartum moms",
        visual_identity: "soft home lighting",
      },
      target_platforms: ["tiktok"],
      target_languages: ["en"],
      video_duration: 45,
    });
  });

  it("maps S3 product catalog and influencer fields to the S3 backend contract", () => {
    const payload = buildScenarioAutoSubmitPayload({
      content_scenario: "influencer_remix",
      video_url: "https://example.com/ugc.mp4",
      influencer_name: "Creator A",
      product_catalog: {
        products: [
          {
            name: "Momcozy M9",
            usps: [{ priority: "P0", text: "hands-free pumping" }],
          },
        ],
      },
    });

    expect(payload).toMatchObject({
      video_url: "https://example.com/ugc.mp4",
      influencer_name: "Creator A",
      product: {
        name: "Momcozy M9",
        usps: [{ priority: "P0", text: "hands-free pumping" }],
      },
    });
    expect(payload).not.toHaveProperty("product_catalog");
  });

  it("converts S4 live shoot aliases and uploaded file paths into footage assets", () => {
    const payload = buildScenarioAutoSubmitPayload({
      content_scenario: "live_shoot_to_video",
      footage_assets: "asset://momcozy/live/store-demo.mp4",
      product_info: { name: "KleanPal Pro" },
      topic: "one day with a newborn",
      brand_guidelines: { brand_name: "Momcozy" },
    });

    expect(payload).toMatchObject({
      footage_assets: [
        {
          path: "asset://momcozy/live/store-demo.mp4",
          source: "guided_form",
        },
      ],
      product_info: {
        name: "KleanPal Pro",
        brand_name: "Momcozy",
      },
      topic: "one day with a newborn",
    });
  });

  it("keeps S5 VLOG model and story fields for async submit", () => {
    const payload = buildScenarioAutoSubmitPayload({
      content_scenario: "brand_vlog",
      brand_id: "momcozy",
      product_sku: {
        name: "M5",
        views: [{ label: "front" }],
      },
      product_views: "asset://momcozy/m5/front.png",
      scene_id: "living-room",
      selected_models: [{ id: "mom" }],
      story_description: "morning bottle cleaning routine",
      video_duration: 30,
    });

    expect(payload).toMatchObject({
      brand_id: "momcozy",
      product_sku: {
        name: "M5",
        views: [
          {
            label: "front",
            imagePath: "asset://momcozy/m5/front.png",
            path: "asset://momcozy/m5/front.png",
          },
        ],
      },
      scene_id: "living-room",
      selected_models: [{ id: "mom" }],
      story_description: "morning bottle cleaning routine",
      video_duration: 30,
    });
  });

  it.each([
    ["influencer_remix", ["week"]],
    ["live_shoot_to_video", ["target_languages", "week"]],
    ["brand_vlog", ["target_platforms", "target_languages", "week"]],
  ])("omits backend-unsupported common fields for %s", (contentScenario, forbiddenKeys) => {
    const payload = buildScenarioAutoSubmitPayload({
      content_scenario: contentScenario,
      target_platforms: ["tiktok"],
      target_languages: ["en"],
      content_calendar_week: "2026-W28",
      product_catalog: { name: "Fixture" },
    });

    for (const key of forbiddenKeys) {
      expect(payload).not.toHaveProperty(key);
    }
  });
});

describe("buildS1EditedStateUpdate", () => {
  it("sends only user-editable fields for one step", () => {
    const payload = buildS1EditedStateUpdate("scripts", [{ text: "edited" }]);

    expect(payload).toEqual({
      steps: {
        scripts: {
          edited: true,
          edited_output: [{ text: "edited" }],
        },
      },
    });
    expect(payload).not.toHaveProperty("current_step");
    expect((payload.steps as Record<string, unknown>).scripts).not.toHaveProperty("status");
    expect((payload.steps as Record<string, unknown>).scripts).not.toHaveProperty("output");
  });
});
