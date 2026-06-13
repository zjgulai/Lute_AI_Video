export type ClipVerificationView = {
  all_ok?: boolean;
};

export type ClipDetailView = {
  duration?: number;
  is_stub?: boolean;
  is_filler?: boolean;
  continuity_frame?: unknown;
  verification?: ClipVerificationView;
};

export type SeedanceClipOutputView = {
  paths: string[];
  details: ClipDetailView[];
  totalDuration: number;
  targetDuration: number;
  hasDurationTarget: boolean;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function numberValue(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function normalizeClipDetail(value: unknown): ClipDetailView {
  const record = isRecord(value) ? value : {};
  const verification = isRecord(record.verification) ? record.verification : {};

  return {
    duration: numberValue(record.duration),
    is_stub: record.is_stub === true,
    is_filler: record.is_filler === true,
    continuity_frame: record.continuity_frame,
    verification: {
      all_ok: typeof verification.all_ok === "boolean" ? verification.all_ok : undefined,
    },
  };
}

export function extractSeedanceClipOutput(output: unknown): SeedanceClipOutputView {
  const record = isRecord(output) ? output : {};
  const hasClipPaths = Array.isArray(record.clip_paths);
  const paths = hasClipPaths
    ? stringList(record.clip_paths)
    : Array.isArray(output)
    ? stringList(output)
    : stringList(record.urls);

  return {
    paths,
    details: hasClipPaths && Array.isArray(record.clip_details)
      ? record.clip_details.map(normalizeClipDetail)
      : [],
    totalDuration: hasClipPaths ? numberValue(record.total_duration) ?? 0 : 0,
    targetDuration: hasClipPaths ? numberValue(record.target_duration) ?? 0 : 0,
    hasDurationTarget: hasClipPaths && (numberValue(record.target_duration) ?? 0) > 0,
  };
}

export function extractTtsAudioPaths(output: unknown): string[] {
  const record = isRecord(output) ? output : {};
  return Array.isArray(output) ? stringList(output) : stringList(record.audio_paths ?? record.urls);
}

export function extractThumbnailImagePaths(output: unknown): string[] {
  const record = isRecord(output) ? output : {};
  return Array.isArray(output)
    ? stringList(output)
    : stringList(record.thumbnail_image_paths ?? record.image_paths ?? record.urls);
}

export function extractFinalVideoPath(output: unknown): string {
  if (typeof output === "string") return output;
  if (Array.isArray(output)) return typeof output[0] === "string" ? output[0] : "";
  const record = isRecord(output) ? output : {};
  return typeof record.final_video_url === "string"
    ? record.final_video_url
    : typeof record.final_video_path === "string"
    ? record.final_video_path
    : typeof record.video_path === "string"
    ? record.video_path
    : "";
}

export function extractRenderJsonPath(output: unknown): string {
  const record = isRecord(output) ? output : {};
  return typeof record.render_json_path === "string" ? record.render_json_path : "";
}
