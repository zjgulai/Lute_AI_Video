import { describe, expect, it } from "vitest";

import { summarizeStepOutputPreview } from "./pipelineOutputPreview";

describe("summarizeStepOutputPreview", () => {
  it("summarizes arrays as item counts", () => {
    expect(summarizeStepOutputPreview([{ id: "a" }, { id: "b" }])).toEqual({
      type: "items",
      count: 2,
    });
  });

  it("prefers audit status and summary before generic field counts", () => {
    expect(summarizeStepOutputPreview({ overall_status: "PASS", summary: "ready" })).toEqual({
      type: "quality_status",
      status: "PASS",
    });
    expect(summarizeStepOutputPreview({ summary: "abcdefghijklmnopqrstuvwxyz", field: true }, 10)).toEqual({
      type: "summary",
      text: "abcdefghij",
    });
  });

  it("falls back to field counts, primitive text, or no preview", () => {
    expect(summarizeStepOutputPreview({ video_path: "/tmp/final.mp4", duration: 30 })).toEqual({
      type: "fields",
      count: 2,
    });
    expect(summarizeStepOutputPreview(12345, 3)).toEqual({
      type: "text",
      text: "123",
    });
    expect(summarizeStepOutputPreview(null)).toBeNull();
    expect(summarizeStepOutputPreview({})).toBeNull();
  });
});
