import { describe, expect, it } from "vitest";

import {
  extractPipelineStepDurations,
  extractPipelineStepOrder,
  extractPipelineSteps,
  extractSoftDegradedReasons,
  normalizeStepByStepStatePayload,
  normalizeWorkflowState,
  normalizeWorkflowStatePayload,
} from "./pipelineState";

describe("pipeline state normalization", () => {
  it("extracts nested response state before normalizing step-by-step state", () => {
    const normalized = normalizeStepByStepStatePayload({
      label: "s1_fixture",
      state: {
        current_step: null,
        mode: "step_by_step",
        steps: {
          strategy: { status: "done", duration_ms: 120 },
          legacy_output_only: "raw output",
        },
        errors: ["first", 42, "second"],
      },
    });

    expect(normalized).toMatchObject({
      current_step: null,
      mode: "step_by_step",
      errors: ["first", "second"],
      steps: {
        strategy: { status: "done", duration_ms: 120 },
        legacy_output_only: { output: "raw output" },
      },
    });
  });

  it("normalizes workflow state metadata used by progress UIs", () => {
    const normalized = normalizeWorkflowState({
      status: "running",
      meta: {
        step_order: ["strategy", 1, "", "scripts"],
        step_durations: {
          strategy: "~5s",
          scripts: "~8s",
          invalid: 12,
        },
      },
      soft_degraded_reasons: [
        { step: "scripts", reason: "fallback", detail: "used cached asset", ignored: true },
        "ignored",
      ],
      steps: {
        strategy: { status: "done" },
      },
    });

    expect(extractPipelineStepOrder(normalized, ["fallback"])).toEqual(["strategy", "scripts"]);
    expect(extractPipelineStepDurations(normalized, { fallback: "~1s" })).toEqual({
      strategy: "~5s",
      scripts: "~8s",
    });
    expect(extractSoftDegradedReasons(normalized.soft_degraded_reasons)).toEqual([
      { step: "scripts", reason: "fallback", detail: "used cached asset" },
    ]);
    expect(extractPipelineSteps(normalized)).toEqual({
      strategy: { status: "done" },
    });
  });

  it("falls back safely for non-object workflow payloads", () => {
    const normalized = normalizeWorkflowStatePayload("not a state");

    expect(normalized).toEqual({
      steps: {},
      errors: [],
      soft_degraded_reasons: [],
    });
    expect(extractPipelineStepOrder(normalized, ["strategy"])).toEqual(["strategy"]);
    expect(extractPipelineStepDurations(normalized, { strategy: "~5s" })).toEqual({
      strategy: "~5s",
    });
  });
});
