import { beforeEach, describe, expect, it } from "vitest";

import { usePipelineStore } from "./usePipelineStore";

describe("pipeline store reset authority", () => {
  beforeEach(() => {
    localStorage.clear();
    usePipelineStore.getState().clearPendingSubmission();
    usePipelineStore.getState().resetAll();
  });

  it("preserves the sole idempotency key during ordinary UI reset", () => {
    const pending = {
      kind: "fast" as const,
      idempotencyKey: "123e4567-e89b-42d3-a456-426614174000",
      createdAt: 1_700_000_000_000,
      phase: "recovering" as const,
    };
    usePipelineStore.getState().setPendingSubmission(pending);

    usePipelineStore.getState().resetAll();

    expect(usePipelineStore.getState().pendingSubmission).toEqual(pending);
  });

  it("clears the idempotency key only through the explicit clear action", () => {
    usePipelineStore.getState().setPendingSubmission({
      kind: "fast",
      idempotencyKey: "123e4567-e89b-42d3-a456-426614174000",
      createdAt: 1_700_000_000_000,
      phase: "bound",
      resourceId: "fast_1_fixture",
    });

    usePipelineStore.getState().clearPendingSubmission();

    expect(usePipelineStore.getState().pendingSubmission).toBeNull();
  });
});
