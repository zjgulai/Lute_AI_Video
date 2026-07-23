import { describe, expect, it } from "vitest";

import { classifyGenerationResult } from "./generationLifecycle";

describe("classifyGenerationResult", () => {
  it.each([
    [
      {
        status: "completed_full",
        lifecycle_status: "completed_full",
        completion_kind: "full_media",
        request_succeeded: true,
        success: true,
        full_media_success: true,
        publish_allowed: false,
      },
      "full",
    ],
    [
      {
        status: "completed_bounded",
        lifecycle_status: "completed_bounded",
        completion_kind: "bounded_media",
        request_succeeded: true,
        success: false,
        full_media_success: false,
        publish_allowed: false,
      },
      "bounded",
    ],
    [
      {
        status: "completed_bounded",
        lifecycle_status: "completed_bounded",
        completion_kind: "no_media",
        request_succeeded: true,
        success: false,
        full_media_success: false,
        publish_allowed: false,
      },
      "bounded",
    ],
    [{ status: "error", request_succeeded: false, success: false }, "error"],
    [{ completion_kind: "execution_failed", success: true }, "error"],
    [{ success: false }, "error"],
    [{ success: true }, "full"],
    [{ briefs: [] }, "error"],
    [
      {
        status: "completed_full",
        lifecycle_status: "completed_full",
        completion_kind: "bounded_media",
        request_succeeded: true,
        success: true,
        full_media_success: true,
      },
      "error",
    ],
    [
      {
        status: "completed_full",
        lifecycle_status: "completed_full",
        completion_kind: "full_media",
        request_succeeded: true,
        success: true,
        full_media_success: false,
      },
      "error",
    ],
    [
      {
        status: "completed_bounded",
        lifecycle_status: "completed_full",
        completion_kind: "full_media",
        request_succeeded: true,
        success: true,
        full_media_success: true,
      },
      "error",
    ],
    [
      {
        status: "completed_bounded",
        lifecycle_status: "completed_bounded",
        completion_kind: "bounded_media",
        request_succeeded: true,
        success: true,
        full_media_success: false,
      },
      "error",
    ],
  ] as const)("classifies %o as %s", (result, expected) => {
    expect(classifyGenerationResult(result)).toBe(expected);
  });
});
