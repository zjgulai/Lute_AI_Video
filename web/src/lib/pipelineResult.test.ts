import { describe, expect, it } from "vitest";

import {
  extractGalleryResultFields,
  normalizePipelineResult,
  normalizePipelineSteps,
} from "./pipelineResult";

describe("pipeline result normalization", () => {
  it("normalizes arbitrary completion payloads into a plain pipeline result", () => {
    const normalized = normalizePipelineResult({
      final_video_path: "/output/final.mp4",
      nested: {
        kept: "value",
        missing: undefined,
        unsafe: () => "ignored",
      },
      items: ["ok", undefined, Symbol("ignored")],
    });

    expect(normalized).toEqual({
      final_video_path: "/output/final.mp4",
      nested: {
        kept: "value",
        missing: null,
        unsafe: null,
      },
      items: ["ok", null, null],
    });
  });

  it("rejects non-object completion payloads", () => {
    expect(normalizePipelineResult(null)).toEqual({});
    expect(normalizePipelineResult(["not", "a", "result"])).toEqual({});
    expect(normalizePipelineResult("done")).toEqual({});
  });

  it("normalizes pipeline step maps without trusting every step value shape", () => {
    expect(
      normalizePipelineSteps({
        strategy: { status: "done", duration_ms: 120 },
        legacy_output_only: "plain output",
      }),
    ).toEqual({
      strategy: { status: "done", duration_ms: 120 },
      legacy_output_only: { output: "plain output" },
    });
    expect(normalizePipelineSteps(["not", "steps"])).toEqual({});
  });

  it("extracts gallery fields from only the supported result shapes", () => {
    const result = normalizePipelineResult({
      briefs: [{ product_name: "Wearable Pump", video_type: "demo" }, "ignored"],
      scripts: [{ product_name: "Fallback Script Product" }],
      thumbnail_image_paths: ["/thumb.png", 42],
      final_video_path: "/final.mp4",
      video_duration: 30,
      audit_report: { overall_score: 0.91 },
    });

    expect(extractGalleryResultFields(result)).toEqual({
      briefs: [{ product_name: "Wearable Pump", video_type: "demo" }],
      scripts: [{ product_name: "Fallback Script Product" }],
      thumbnailImagePaths: ["/thumb.png"],
      finalVideoPath: "/final.mp4",
      videoDuration: 30,
      auditScore: 0.91,
    });
  });
});
