import { describe, expect, it } from "vitest";
import { applyGuidedContinuityDefaults, normalizeContinuityMode } from "./guidedScenarioConfig";

describe("guidedScenarioConfig", () => {
  it("normalizes unknown continuity mode to standard", () => {
    expect(normalizeContinuityMode("high_quality")).toBe("high_quality");
    expect(normalizeContinuityMode("fast")).toBe("standard");
    expect(normalizeContinuityMode(undefined)).toBe("standard");
  });

  it.each([
    ["product_direct", "match_cut"],
    ["brand_campaign", "match_cut"],
    ["influencer_remix", "match_cut"],
    ["live_shoot_to_video", "match_cut"],
    ["brand_vlog", "soft_crossfade"],
  ])("adds continuity defaults for %s", (scene, transitionStyle) => {
    const config = applyGuidedContinuityDefaults(
      { content_scenario: scene },
      scene,
      { continuity_mode: "high_quality" },
    );

    expect(config).toMatchObject({
      content_scenario: scene,
      continuity_mode: "high_quality",
      storyboard_grid: "12",
      transition_style: transitionStyle,
    });
  });

  it("does not alter unsupported scenes", () => {
    expect(applyGuidedContinuityDefaults({ content_scenario: "fast_mode" }, "fast_mode", {})).toEqual({
      content_scenario: "fast_mode",
    });
  });
});
