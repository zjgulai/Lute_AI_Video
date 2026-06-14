import { describe, expect, it } from "vitest";
import { sceneToPath, sceneToScenarioId } from "./scenarioRouting";

describe("scenarioRouting", () => {
  it.each([
    ["product_direct", "s1"],
    ["brand_campaign", "s2"],
    ["influencer_remix", "s3"],
    ["live_shoot", "s4"],
    ["live_shoot_to_video", "s4"],
    ["brand_vlog", "s5"],
  ])("maps %s to %s", (scene, scenarioId) => {
    expect(sceneToScenarioId(scene)).toBe(scenarioId);
  });

  it("falls back unknown scenes to S1", () => {
    expect(sceneToScenarioId("unknown")).toBe("s1");
  });

  it.each([
    ["product_direct", "/s1"],
    ["brand_campaign", "/s2"],
    ["influencer_remix", "/s3"],
    ["live_shoot", "/s4"],
    ["live_shoot_to_video", "/s4"],
    ["brand_vlog", "/s5"],
    ["fast_mode", "/fast"],
  ])("maps %s to path %s", (scene, path) => {
    expect(sceneToPath(scene)).toBe(path);
  });
});
