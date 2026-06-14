type SceneConfig = Record<string, unknown>;

function continuityGenerationMode(config: SceneConfig): string {
  if (typeof config.continuity_generation_mode === "string" && config.continuity_generation_mode) {
    return config.continuity_generation_mode;
  }
  return config.continuity_mode === "high_quality" ? "high_quality" : "standard";
}

export function withScenarioContinuityConfig<T extends Record<string, unknown>>(
  config: SceneConfig,
  payload: T,
): T {
  return {
    ...payload,
    enable_media_synthesis: config.enable_media_synthesis ?? true,
    continuity_mode: config.continuity_mode ?? true,
    continuity_generation_mode: continuityGenerationMode(config),
    storyboard_grid: config.storyboard_grid ?? 12,
    clip_group_size: config.clip_group_size ?? 3,
    transition_style: typeof config.transition_style === "string" && config.transition_style
      ? config.transition_style
      : "match_cut",
  };
}
