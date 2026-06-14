import type { PipelineResult } from "@/stores/usePipelineStore";

type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue };
export type PipelineStepRecord = Record<string, unknown>;
export type PipelineSteps = Record<string, PipelineStepRecord>;

export type GalleryResultFields = {
  briefs: Record<string, unknown>[];
  scripts: Record<string, unknown>[];
  thumbnailImagePaths: string[];
  finalVideoPath: string;
  videoDuration: number;
  auditScore: number;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function normalizeJsonValue(value: unknown): JsonValue {
  if (value === null || value === undefined) return null;

  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return value;
  }

  if (Array.isArray(value)) {
    return value.map((item) => normalizeJsonValue(item));
  }

  if (isRecord(value)) {
    return Object.fromEntries(
      Object.entries(value).map(([key, entry]) => [key, normalizeJsonValue(entry)]),
    );
  }

  return null;
}

export function normalizePipelineResult(value: unknown): PipelineResult {
  const normalized = normalizeJsonValue(value);
  return isRecord(normalized) ? normalized : {};
}

export function normalizePipelineSteps(value: unknown): PipelineSteps {
  if (!isRecord(value)) return {};

  return Object.fromEntries(
    Object.entries(value).map(([stepName, stepState]) => [
      stepName,
      isRecord(stepState) ? stepState : { output: stepState },
    ]),
  );
}

function asRecordArray(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter(isRecord) : [];
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function asNumber(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

export function extractGalleryResultFields(result: PipelineResult): GalleryResultFields {
  const auditReport = isRecord(result.audit_report) ? result.audit_report : {};

  return {
    briefs: asRecordArray(result.briefs),
    scripts: asRecordArray(result.scripts),
    thumbnailImagePaths: asStringArray(result.thumbnail_image_paths),
    finalVideoPath: asString(result.final_video_path),
    videoDuration: asNumber(result.video_duration),
    auditScore: asNumber(auditReport.overall_score),
  };
}
