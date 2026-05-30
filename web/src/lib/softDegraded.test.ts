import { describe, expect, it } from "vitest";

import {
  getSoftDegradedDetailLabel,
  getSoftDegradedReasonLabel,
  getSoftDegradedStepLabel,
  getSoftDegradedSummary,
} from "./softDegraded";

const dictionary: Record<string, string> = {
  "step.continuity_storyboard_grid": "连贯性分镜",
  "degraded.reason.continuity_skill_fallback": "已使用 continuity 降级兜底结果",
  "degraded.detail.continuity_skill_fallback": "continuity 产物已用本地兜底结果替代，请重点检查画面连贯性。",
  "degraded.reason.unknown": "已使用通用降级结果",
};

const t = (key: string, fallback?: string): string => dictionary[key] ?? fallback ?? key;

describe("soft degraded helpers", () => {
  it("maps known reason codes to user-facing text", () => {
    expect(getSoftDegradedReasonLabel("continuity_skill_fallback", t)).toBe("已使用 continuity 降级兜底结果");
  });

  it("maps known step codes to user-facing text", () => {
    expect(getSoftDegradedStepLabel("continuity_storyboard_grid", t)).toBe("连贯性分镜");
  });

  it("falls back to translated unknown reason", () => {
    expect(getSoftDegradedReasonLabel(undefined, t)).toBe("已使用通用降级结果");
  });

  it("does not expose unknown backend reason codes", () => {
    expect(getSoftDegradedReasonLabel("internal_backend_code", t)).toBe("已使用通用降级结果");
  });

  it("maps detail only for known reason codes", () => {
    expect(getSoftDegradedDetailLabel("continuity_skill_fallback", t)).toBe(
      "continuity 产物已用本地兜底结果替代，请重点检查画面连贯性。",
    );
    expect(getSoftDegradedDetailLabel("internal_backend_code", t)).toBe("");
  });

  it("formats a summary payload", () => {
    expect(
      getSoftDegradedSummary(
        {
          step: "continuity_storyboard_grid",
          reason: "continuity_skill_fallback",
          detail: "mock fallback used with internal_backend_code",
        },
        t,
      ),
    ).toEqual({
      stepLabel: "连贯性分镜",
      reasonLabel: "已使用 continuity 降级兜底结果",
      detail: "continuity 产物已用本地兜底结果替代，请重点检查画面连贯性。",
    });
  });
});
