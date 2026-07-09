import { describe, expect, it } from "vitest";

import { buildScenarioAutoSubmitPayload } from "./scenarioPayload";

describe("buildScenarioAutoSubmitPayload", () => {
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
});
