import { describe, expect, it } from "vitest";
import { buildScenarioAutoSubmitPayload } from "./scenarioPayload";
import { withScenarioContinuityConfig } from "./scenarioContinuity";

describe("withScenarioContinuityConfig", () => {
  it("preserves explicit high-quality continuity settings", () => {
    const payload = withScenarioContinuityConfig(
      {
        continuity_mode: "high_quality",
        storyboard_grid: "12",
        clip_group_size: 4,
        transition_style: "soft_crossfade",
      },
      { product_catalog: { products: [] } },
    );

    expect(payload).toMatchObject({
      continuity_mode: "high_quality",
      continuity_generation_mode: "high_quality",
      storyboard_grid: "12",
      clip_group_size: 4,
      transition_style: "soft_crossfade",
    });
  });

  it("adds fail-closed generation defaults when a scene omits safety intent", () => {
    const payload = withScenarioContinuityConfig({}, { product_catalog: { products: [] } });

    expect(payload).toMatchObject({
      continuity_mode: true,
      continuity_generation_mode: "standard",
      storyboard_grid: 12,
      clip_group_size: 3,
      transition_style: "match_cut",
      enable_media_synthesis: false,
      artifact_disposition: "pending_review",
      provider_max_retries: 0,
    });
  });

  it("preserves an explicit provider-on click intent including exact retry zero", () => {
    const payload = withScenarioContinuityConfig(
      {
        enable_media_synthesis: true,
        artifact_disposition: "pending_review",
        provider_max_retries: 0,
      },
      { product_catalog: { products: [] } },
    );

    expect(payload.enable_media_synthesis).toBe(true);
    expect(payload.artifact_disposition).toBe("pending_review");
    expect(payload.provider_max_retries).toBe(0);
  });

  it.each(["brand_campaign", "influencer_remix", "live_shoot_to_video", "brand_vlog"])(
    "does not attach S1-only continuity controls to %s",
    (contentScenario) => {
      const payload = withScenarioContinuityConfig(
        {
          content_scenario: contentScenario,
          continuity_mode: "high_quality",
          storyboard_grid: 12,
          clip_group_size: 4,
          transition_style: "soft_crossfade",
        },
        { scenario_fixture: true },
      );

      expect(payload).toMatchObject({
        scenario_fixture: true,
        enable_media_synthesis: false,
        artifact_disposition: "pending_review",
        provider_max_retries: 0,
      });
      expect(payload).not.toHaveProperty("continuity_mode");
      expect(payload).not.toHaveProperty("continuity_generation_mode");
      expect(payload).not.toHaveProperty("storyboard_grid");
      expect(payload).not.toHaveProperty("clip_group_size");
      expect(payload).not.toHaveProperty("transition_style");
    },
  );

  it.each([
    [
      "product_direct",
      [
        "artifact_disposition", "clip_group_size", "continuity_generation_mode",
        "continuity_mode", "enable_media_synthesis", "product_catalog",
        "provider_max_retries", "storyboard_grid", "target_languages",
        "target_platforms", "transition_style", "video_duration", "week",
      ],
    ],
    [
      "brand_campaign",
      [
        "artifact_disposition", "brand_package", "enable_media_synthesis",
        "provider_max_retries", "target_languages", "target_platforms",
        "video_duration", "week",
      ],
    ],
    [
      "influencer_remix",
      [
        "artifact_disposition", "brief_id", "enable_media_synthesis",
        "influencer_name", "product", "provider_max_retries", "target_languages",
        "target_platforms", "video_duration", "video_url",
      ],
    ],
    [
      "live_shoot_to_video",
      [
        "artifact_disposition", "brand_guidelines", "enable_media_synthesis",
        "footage_assets", "product_info", "provider_max_retries", "target_platforms",
        "topic", "video_duration",
      ],
    ],
    [
      "brand_vlog",
      [
        "artifact_disposition", "brand_id", "enable_media_synthesis", "product_sku",
        "provider_max_retries", "scene_id", "selected_models", "story_description",
        "video_duration",
      ],
    ],
  ])("emits the exact backend wire keys for %s", (contentScenario, expectedKeys) => {
    const config = {
      content_scenario: contentScenario,
      product_catalog: { name: "Fixture" },
      target_platforms: ["tiktok"],
      target_languages: ["en"],
      content_calendar_week: "2026-W28",
    };
    const composed = withScenarioContinuityConfig(
      config,
      buildScenarioAutoSubmitPayload(config),
    );
    const wirePayload = JSON.parse(JSON.stringify(composed)) as Record<string, unknown>;

    expect(Object.keys(wirePayload).sort()).toEqual([...expectedKeys].sort());
  });
});
