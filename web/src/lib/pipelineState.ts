import { normalizePipelineSteps, type PipelineSteps } from "@/lib/pipelineResult";
import type { StepByStepState, WorkflowState } from "@/stores/usePipelineStore";

export type SoftDegradedReason = {
  step?: string;
  reason?: string;
  detail?: string;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function statePayload(value: unknown): unknown {
  return isRecord(value) && isRecord(value.state) ? value.state : value;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function stringMap(value: unknown): Record<string, string> {
  if (!isRecord(value)) return {};
  return Object.fromEntries(
    Object.entries(value).filter((entry): entry is [string, string] => typeof entry[1] === "string"),
  );
}

export function extractSoftDegradedReasons(value: unknown): SoftDegradedReason[] {
  if (!Array.isArray(value)) return [];

  return value
    .filter(isRecord)
    .map((item) => ({
      step: typeof item.step === "string" ? item.step : undefined,
      reason: typeof item.reason === "string" ? item.reason : undefined,
      detail: typeof item.detail === "string" ? item.detail : undefined,
    }));
}

export function normalizeStepByStepState(value: unknown): StepByStepState {
  const record = isRecord(value) ? value : {};
  const normalized: StepByStepState = {
    ...record,
    steps: normalizePipelineSteps(record.steps),
    errors: stringList(record.errors),
    soft_degraded_reasons: extractSoftDegradedReasons(record.soft_degraded_reasons),
  };

  if (typeof record.current_step === "string" || record.current_step === null) {
    normalized.current_step = record.current_step;
  }
  if (isRecord(record.gates)) {
    normalized.gates = record.gates;
  }
  if (typeof record.mode === "string") {
    normalized.mode = record.mode;
  }
  if (typeof record.pipeline_degraded === "boolean") {
    normalized.pipeline_degraded = record.pipeline_degraded;
  }
  if (typeof record.degraded_reason === "string" || record.degraded_reason === null) {
    normalized.degraded_reason = record.degraded_reason;
  }

  return normalized;
}

export function normalizeStepByStepStatePayload(value: unknown): StepByStepState {
  return normalizeStepByStepState(statePayload(value));
}

export function normalizeWorkflowState(value: unknown): WorkflowState {
  const record = isRecord(value) ? value : {};
  const normalized: WorkflowState = {
    ...record,
    steps: normalizePipelineSteps(record.steps),
    errors: stringList(record.errors),
    soft_degraded_reasons: extractSoftDegradedReasons(record.soft_degraded_reasons),
  };

  if (typeof record.current_step === "string" || record.current_step === null) {
    normalized.current_step = record.current_step;
  }
  if (typeof record.status === "string") {
    normalized.status = record.status;
  }
  if (typeof record.pipeline_degraded === "boolean") {
    normalized.pipeline_degraded = record.pipeline_degraded;
  }
  if (typeof record.degraded_reason === "string" || record.degraded_reason === null) {
    normalized.degraded_reason = record.degraded_reason;
  }

  return normalized;
}

export function normalizeWorkflowStatePayload(value: unknown): WorkflowState {
  return normalizeWorkflowState(statePayload(value));
}

export function extractPipelineSteps(value: unknown): PipelineSteps {
  return normalizePipelineSteps(isRecord(value) ? value.steps : undefined);
}

export function extractPipelineStepOrder(value: unknown, fallback: string[]): string[] {
  const meta = isRecord(value) ? value.meta : undefined;
  const order = isRecord(meta) ? meta.step_order : undefined;
  const normalized = stringList(order).filter((item) => item.length > 0);
  return normalized.length > 0 ? normalized : fallback;
}

export function extractPipelineStepDurations(
  value: unknown,
  fallback: Record<string, string>,
): Record<string, string> {
  const meta = isRecord(value) ? value.meta : undefined;
  const durations = isRecord(meta) ? stringMap(meta.step_durations) : {};
  return Object.keys(durations).length > 0 ? durations : fallback;
}
