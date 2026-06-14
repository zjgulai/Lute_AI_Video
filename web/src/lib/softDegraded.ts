export interface SoftDegradedReason {
  step?: string;
  reason?: string;
  detail?: string;
}

type Translate = (key: string, fallback?: string) => string;

const STEP_LABEL_KEYS: Record<string, string> = {
  strategy: "step.strategy",
  scripts: "step.scripts",
  compliance: "step.compliance",
  storyboards: "step.storyboards",
  continuity_storyboard_grid: "step.continuity_storyboard_grid",
  video_analysis: "step.video_analysis",
  character_identity: "step.character_identity",
  remix_script: "step.remix_script",
  keyframe_images: "step.keyframe_images",
  video_prompts: "step.video_prompts",
  thumbnail_prompts: "step.thumbnail_prompts",
  seedance_clips: "step.seedance_clips",
  tts_audio: "step.tts_audio",
  thumbnail_images: "step.thumbnail_images",
  assemble_final: "step.assemble_final",
  audit: "step.audit",
  vlog_strategy: "step.vlog_strategy",
  thumbnails: "step.thumbnails",
};

const REASON_LABEL_KEYS: Record<string, string> = {
  continuity_skill_fallback: "degraded.reason.continuity_skill_fallback",
  continuity_skill_execution_failed: "degraded.reason.continuity_skill_execution_failed",
  video_analysis_failed_using_fallback: "degraded.reason.video_analysis_failed_using_fallback",
  footage_invalid_using_stock_fallback: "degraded.reason.footage_invalid_using_stock_fallback",
  footage_invalid_no_stock_fallback: "degraded.reason.footage_invalid_no_stock_fallback",
  s3_viral_extract_disabled_adr004: "degraded.reason.s3_viral_extract_disabled_adr004",
};

export function getSoftDegradedStepLabel(step: string | undefined, t: Translate): string {
  if (!step) return "";
  const key = STEP_LABEL_KEYS[step];
  return key ? t(key, step) : step;
}

export function getSoftDegradedReasonLabel(reason: string | undefined, t: Translate): string {
  if (!reason) return t("degraded.reason.unknown");
  const key = REASON_LABEL_KEYS[reason];
  return key ? t(key, t("degraded.reason.unknown")) : t("degraded.reason.unknown");
}

export function getSoftDegradedDetailLabel(reason: string | undefined, t: Translate): string {
  if (!reason || !REASON_LABEL_KEYS[reason]) return "";
  return t(`degraded.detail.${reason}`, "");
}

export function getSoftDegradedSummary(
  entry: SoftDegradedReason | undefined,
  t: Translate,
): { stepLabel: string; reasonLabel: string; detail: string } {
  return {
    stepLabel: getSoftDegradedStepLabel(entry?.step, t),
    reasonLabel: getSoftDegradedReasonLabel(entry?.reason, t),
    detail: getSoftDegradedDetailLabel(entry?.reason, t),
  };
}
