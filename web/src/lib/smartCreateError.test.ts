import { describe, expect, it, vi } from "vitest";

import { handleSmartCreateStageError } from "./smartCreateError";

describe("handleSmartCreateStageError", () => {
  it("stops generation, clears active pipeline, and shows the first error", () => {
    const stopGenerating = vi.fn();
    const clearActivePipeline = vi.fn();
    const showToast = vi.fn();
    const t = (key: string): string => ({ "toast.execFailed": "执行失败" })[key] ?? key;

    handleSmartCreateStageError(["pipeline degraded"], {
      stopGenerating,
      clearActivePipeline,
      showToast,
      t,
    });

    expect(stopGenerating).toHaveBeenCalledOnce();
    expect(clearActivePipeline).toHaveBeenCalledOnce();
    expect(showToast).toHaveBeenCalledWith("执行失败: pipeline degraded", "error");
  });

  it("falls back to translated execution failure text when no error detail is provided", () => {
    const stopGenerating = vi.fn();
    const clearActivePipeline = vi.fn();
    const showToast = vi.fn();
    const t = (key: string): string => ({ "toast.execFailed": "执行失败" })[key] ?? key;

    handleSmartCreateStageError([], {
      stopGenerating,
      clearActivePipeline,
      showToast,
      t,
    });

    expect(showToast).toHaveBeenCalledWith("执行失败: 执行失败", "error");
  });
});
