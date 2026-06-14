import { describe, expect, it } from "vitest";
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

  it("adds safe defaults when a scene omits continuity settings", () => {
    const payload = withScenarioContinuityConfig({}, { product_catalog: { products: [] } });

    expect(payload).toMatchObject({
      continuity_mode: true,
      continuity_generation_mode: "standard",
      storyboard_grid: 12,
      clip_group_size: 3,
      transition_style: "match_cut",
      enable_media_synthesis: true,
    });
  });
});
