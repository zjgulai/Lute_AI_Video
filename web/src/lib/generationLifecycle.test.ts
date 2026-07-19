import { describe, expect, it } from "vitest";

import { classifyGenerationResult } from "./generationLifecycle";

describe("classifyGenerationResult", () => {
  it.each([
    [{ status: "completed_full", success: true, full_media_success: true }, "full"],
    [
      {
        status: "completed_bounded",
        completion_kind: "bounded_media",
        request_succeeded: true,
        success: false,
        full_media_success: false,
      },
      "bounded",
    ],
    [
      {
        lifecycle_status: "completed_bounded",
        completion_kind: "no_media",
        request_succeeded: true,
        success: false,
      },
      "bounded",
    ],
    [{ status: "error", request_succeeded: false, success: false }, "error"],
    [{ completion_kind: "execution_failed", success: true }, "error"],
    [{ success: false }, "error"],
    [{ briefs: [] }, "full"],
  ] as const)("classifies %o as %s", (result, expected) => {
    expect(classifyGenerationResult(result)).toBe(expected);
  });
});
