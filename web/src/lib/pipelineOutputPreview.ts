export type StepOutputPreview =
  | { type: "items"; count: number }
  | { type: "quality_status"; status: string }
  | { type: "summary"; text: string }
  | { type: "fields"; count: number }
  | { type: "text"; text: string };

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function truncateText(value: string, maxLength: number): string {
  return value.slice(0, Math.max(0, maxLength));
}

export function summarizeStepOutputPreview(
  output: unknown,
  maxTextLength = 60,
): StepOutputPreview | null {
  if (output === null || output === undefined || output === "") return null;

  if (Array.isArray(output)) {
    return { type: "items", count: output.length };
  }

  if (isRecord(output)) {
    if (typeof output.overall_status === "string" && output.overall_status.length > 0) {
      return { type: "quality_status", status: output.overall_status };
    }

    if (typeof output.summary === "string" && output.summary.length > 0) {
      return { type: "summary", text: truncateText(output.summary, maxTextLength) };
    }

    const fieldCount = Object.keys(output).length;
    return fieldCount > 0 ? { type: "fields", count: fieldCount } : null;
  }

  return { type: "text", text: truncateText(String(output), maxTextLength) };
}
