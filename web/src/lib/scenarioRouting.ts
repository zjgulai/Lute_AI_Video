const SCENE_TO_SCENARIO_ID: Record<string, string> = {
  product_direct: "s1",
  brand_campaign: "s2",
  influencer_remix: "s3",
  live_shoot: "s4",
  live_shoot_to_video: "s4",
  brand_vlog: "s5",
};

const SCENE_TO_PATH: Record<string, string> = {
  product_direct: "/s1",
  brand_campaign: "/s2",
  influencer_remix: "/s3",
  live_shoot: "/s4",
  live_shoot_to_video: "/s4",
  brand_vlog: "/s5",
  fast_mode: "/fast",
};

export function sceneToScenarioId(scene: string): string {
  return SCENE_TO_SCENARIO_ID[scene] || "s1";
}

export function sceneToPath(scene: string): string | undefined {
  return SCENE_TO_PATH[scene];
}
