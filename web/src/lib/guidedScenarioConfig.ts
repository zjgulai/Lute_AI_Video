type GuidedValues = Record<string, string>;

const CONTINUITY_SCENES = new Set([
  "product_direct",
  "brand_campaign",
  "influencer_remix",
  "live_shoot_to_video",
  "brand_vlog",
]);

export function normalizeContinuityMode(value?: string): "standard" | "high_quality" {
  return value === "high_quality" ? "high_quality" : "standard";
}

export function applyGuidedContinuityDefaults(
  config: Record<string, unknown>,
  scene: string,
  values: GuidedValues,
): Record<string, unknown> {
  if (!CONTINUITY_SCENES.has(scene)) return config;

  return {
    ...config,
    storyboard_grid: "12",
    transition_style: scene === "brand_vlog" ? "soft_crossfade" : "match_cut",
    continuity_mode: normalizeContinuityMode(values.continuity_mode),
  };
}
