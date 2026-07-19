import {
  normalizeGenerationSafetyIntent,
  type GenerationSafetyIntent,
} from "./scenarioPayload";

type SceneConfig = Record<string, unknown>;

type ScenarioContinuityPayload = GenerationSafetyIntent & {
  continuity_mode: unknown;
  continuity_generation_mode: string;
  storyboard_grid: unknown;
  clip_group_size: unknown;
  transition_style: string;
};

type ScenarioPayload = GenerationSafetyIntent & Partial<ScenarioContinuityPayload>;

function continuityGenerationMode(config: SceneConfig): string {
  if (typeof config.continuity_generation_mode === "string" && config.continuity_generation_mode) {
    return config.continuity_generation_mode;
  }
  return config.continuity_mode === "high_quality" ? "high_quality" : "standard";
}

export function withScenarioContinuityConfig<T extends Record<string, unknown>>(
  config: SceneConfig,
  payload: T,
): T & ScenarioPayload {
  const safePayload = {
    ...payload,
    ...normalizeGenerationSafetyIntent(config),
  };
  const scenario = typeof config.content_scenario === "string"
    ? config.content_scenario
    : "product_direct";
  if (scenario !== "product_direct" && scenario !== "s1") {
    return safePayload;
  }
  return {
    ...safePayload,
    continuity_mode: config.continuity_mode ?? true,
    continuity_generation_mode: continuityGenerationMode(config),
    storyboard_grid: config.storyboard_grid ?? 12,
    clip_group_size: config.clip_group_size ?? 3,
    transition_style: typeof config.transition_style === "string" && config.transition_style
      ? config.transition_style
      : "match_cut",
  };
}
