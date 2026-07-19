import { act } from "react";
import { createRoot } from "react-dom/client";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n/I18nProvider";
import { usePipelineStore } from "@/stores/usePipelineStore";
import FastModePanel from "./FastModePanel";

const apiMocks = vi.hoisted(() => ({
  submitFastMode: vi.fn(),
  pollFastStatus: vi.fn(),
  getSubmissionByIdempotencyKey: vi.fn(),
  isApiError: vi.fn(() => false),
}));

vi.mock("./api", () => ({
  submitFastMode: apiMocks.submitFastMode,
  pollFastStatus: apiMocks.pollFastStatus,
  getSubmissionByIdempotencyKey: apiMocks.getSubmissionByIdempotencyKey,
  isDemoMode: () => false,
  isApiError: apiMocks.isApiError,
  resolveMediaPreview: (url: string) => ({ kind: "runtime", url }),
}));

vi.mock("./RuntimeMediaVideo", () => ({
  default: ({ src }: { src: string }) => (
    <video data-testid="runtime-video" data-src={src} />
  ),
}));

async function renderFastModePanel() {
  localStorage.setItem("app-locale", "zh");
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(
      <I18nProvider>
        <FastModePanel />
      </I18nProvider>,
    );
  });
  return {
    container,
    cleanup: () => {
      act(() => root.unmount());
      document.body.removeChild(container);
    },
  };
}

describe("FastModePanel lifecycle presentation", () => {
  beforeEach(() => {
    localStorage.clear();
    usePipelineStore.getState().clearPendingSubmission();
    usePipelineStore.getState().resetAll();
    vi.clearAllMocks();
    apiMocks.isApiError.mockReturnValue(false);
    apiMocks.submitFastMode.mockResolvedValue({
      task_id: "fast_1_abcd",
      status: "queued",
      started_at_unix: 1,
    });
  });

  it("persists a key before submit and recovers an ambiguous response by GET", async () => {
    let pendingAtSubmit: ReturnType<typeof usePipelineStore.getState>["pendingSubmission"] = null;
    let persistedAtSubmit: Record<string, unknown> | null = null;
    let submittedKey = "";
    apiMocks.submitFastMode.mockImplementation(async (
      _body: unknown,
      options: { idempotencyKey: string },
    ) => {
      submittedKey = options.idempotencyKey;
      pendingAtSubmit = usePipelineStore.getState().pendingSubmission;
      const raw = localStorage.getItem("ai-video-pipeline-store");
      persistedAtSubmit = raw
        ? (JSON.parse(raw) as { state?: { pendingSubmission?: Record<string, unknown> } })
            .state?.pendingSubmission ?? null
        : null;
      throw new TypeError("Failed to fetch");
    });
    apiMocks.getSubmissionByIdempotencyKey.mockResolvedValue({
      resource_type: "fast",
      resource_id: "fast_original",
      scenario: "fast",
      status: "queued",
      submit_response: {
        task_id: "fast_original",
        status: "queued",
        started_at_unix: 1,
      },
      result_snapshot: null,
    });
    apiMocks.pollFastStatus.mockResolvedValue({
      status: "completed_bounded",
      lifecycle_status: "completed_bounded",
      completion_kind: "no_media",
      request_succeeded: true,
      success: false,
      full_media_success: false,
      pipeline_complete: false,
      publish_allowed: false,
      delivery_accepted: false,
      video_path: "",
      video_url: "",
      filename: "",
      llm_prompt: "prompt",
      scene_description: "scene",
      user_prompt: "prompt",
      duration_seconds: 10,
      file_size_bytes: 0,
      generation_time_ms: 10,
      timing: { llm_ms: 1, video_ms: 9, tts_ms: 0 },
      model_info: { llm: "fake", video: "fake", tts: null },
      is_stub: true,
      tts_path: null,
    });

    const { container, cleanup } = await renderFastModePanel();
    const textarea = container.querySelector("textarea");
    await act(async () => {
      const valueSetter = Object.getOwnPropertyDescriptor(
        HTMLTextAreaElement.prototype,
        "value",
      )?.set;
      valueSetter?.call(textarea, "safe object shot");
      textarea?.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => {
      container.querySelector<HTMLButtonElement>("button.apple-btn-primary")?.click();
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(pendingAtSubmit).toMatchObject({
      kind: "fast",
      phase: "submitting",
    });
    expect(persistedAtSubmit).toMatchObject({
      kind: "fast",
      phase: "submitting",
      idempotencyKey: submittedKey,
    });
    expect(apiMocks.submitFastMode).toHaveBeenCalledTimes(1);
    expect(apiMocks.getSubmissionByIdempotencyKey).toHaveBeenCalledTimes(1);
    expect(apiMocks.pollFastStatus).toHaveBeenCalledWith(
      "fast_original",
      expect.any(Object),
    );
    cleanup();
  });

  it("reload recovery performs GET/status only and never submits", async () => {
    usePipelineStore.getState().setPendingSubmission({
      kind: "fast",
      idempotencyKey: "123e4567-e89b-42d3-a456-426614174000",
      createdAt: Date.now(),
      phase: "unknown",
    });
    apiMocks.getSubmissionByIdempotencyKey.mockResolvedValue({
      resource_type: "fast",
      resource_id: "fast_reloaded",
      scenario: "fast",
      status: "queued",
      submit_response: { task_id: "fast_reloaded", status: "queued" },
      result_snapshot: null,
    });
    apiMocks.pollFastStatus.mockResolvedValue({
      status: "completed_bounded",
      lifecycle_status: "completed_bounded",
      completion_kind: "no_media",
      request_succeeded: true,
      success: false,
      video_path: "",
      video_url: "",
      filename: "",
      llm_prompt: "prompt",
      scene_description: "scene",
      user_prompt: "prompt",
      duration_seconds: 10,
      file_size_bytes: 0,
      generation_time_ms: 10,
      timing: { llm_ms: 1, video_ms: 9, tts_ms: 0 },
      model_info: { llm: "fake", video: "fake", tts: null },
      is_stub: true,
      tts_path: null,
    });

    const { cleanup } = await renderFastModePanel();
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(apiMocks.submitFastMode).not.toHaveBeenCalled();
    expect(apiMocks.getSubmissionByIdempotencyKey).toHaveBeenCalledTimes(1);
    expect(apiMocks.pollFastStatus).toHaveBeenCalledWith(
      "fast_reloaded",
      expect.any(Object),
    );
    cleanup();
  });

  it("shows a 409 conflict while preserving the original key and blocks replacement submit", async () => {
    apiMocks.isApiError.mockReturnValue(true);
    apiMocks.submitFastMode.mockRejectedValue(Object.assign(new Error("payload conflict"), {
      name: "ApiError",
      info: {
        status: 409,
        code: "idempotency_payload_conflict",
        message: "payload conflict",
        fieldErrors: {},
        retryAfterSec: null,
      },
    }));
    const { container, cleanup } = await renderFastModePanel();
    const textarea = container.querySelector("textarea");
    await act(async () => {
      const valueSetter = Object.getOwnPropertyDescriptor(
        HTMLTextAreaElement.prototype,
        "value",
      )?.set;
      valueSetter?.call(textarea, "safe object shot");
      textarea?.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => {
      container.querySelector<HTMLButtonElement>("button.apple-btn-primary")?.click();
      await Promise.resolve();
      await Promise.resolve();
    });

    const preservedKey = usePipelineStore.getState().pendingSubmission?.idempotencyKey;
    expect(preservedKey).toMatch(/^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$/);
    expect(usePipelineStore.getState().pendingSubmission).toMatchObject({
      idempotencyKey: preservedKey,
      phase: "unknown",
    });
    expect(container.textContent).toContain("提交标识与请求不一致");
    expect(apiMocks.getSubmissionByIdempotencyKey).not.toHaveBeenCalled();
    expect(apiMocks.submitFastMode).toHaveBeenCalledTimes(1);
    expect(container.querySelector<HTMLButtonElement>("button.apple-btn-primary")?.disabled).toBe(true);
    cleanup();
  });

  it("aborts Fast status GET polling when reload recovery stops waiting", async () => {
    usePipelineStore.getState().setPendingSubmission({
      kind: "fast",
      idempotencyKey: "123e4567-e89b-42d3-a456-426614174000",
      createdAt: Date.now(),
      phase: "unknown",
    });
    apiMocks.getSubmissionByIdempotencyKey.mockResolvedValue({
      resource_type: "fast",
      resource_id: "fast_waiting",
      scenario: "fast",
      status: "queued",
      submit_response: { task_id: "fast_waiting", status: "queued" },
      result_snapshot: null,
    });
    let statusSignal: AbortSignal | undefined;
    apiMocks.pollFastStatus.mockImplementation((
      _taskId: string,
      options?: { signal?: AbortSignal },
    ) => {
      statusSignal = options?.signal;
      return new Promise((_resolve, reject) => {
        statusSignal?.addEventListener("abort", () => {
          reject(statusSignal?.reason ?? new DOMException("Stopped", "AbortError"));
        }, { once: true });
      });
    });

    const { container, cleanup } = await renderFastModePanel();
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });
    const stopButton = Array.from(container.querySelectorAll("button")).find(
      (button) => /停止等待|Stop waiting/.test(button.textContent || ""),
    );
    expect(stopButton).toBeTruthy();

    await act(async () => {
      stopButton?.click();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(statusSignal).toBeDefined();
    expect(statusSignal?.aborted).toBe(true);
    expect(container.textContent).toMatch(/已停止浏览器等待|Browser waiting stopped/);
    cleanup();
  });

  it("handles a known Fast terminal failure and clears the pending key", async () => {
    apiMocks.pollFastStatus.mockRejectedValue(Object.assign(new Error("fast_generation_failed"), {
      name: "FastTerminalError",
    }));
    const { container, cleanup } = await renderFastModePanel();
    const textarea = container.querySelector("textarea");
    await act(async () => {
      const valueSetter = Object.getOwnPropertyDescriptor(
        HTMLTextAreaElement.prototype,
        "value",
      )?.set;
      valueSetter?.call(textarea, "safe object shot");
      textarea?.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => {
      container.querySelector<HTMLButtonElement>("button.apple-btn-primary")?.click();
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(usePipelineStore.getState().pendingSubmission).toBeNull();
    expect(container.textContent).toContain("fast_generation_failed");
    expect(container.textContent).not.toContain("任务状态暂时无法确认");
    cleanup();
  });

  it("shows a bounded result with valid media without calling it a failure", async () => {
    apiMocks.pollFastStatus.mockResolvedValue({
      status: "completed_bounded",
      lifecycle_status: "completed_bounded",
      completion_kind: "bounded_media",
      request_succeeded: true,
      success: false,
      full_media_success: false,
      pipeline_complete: false,
      publish_allowed: false,
      delivery_accepted: false,
      video_path: "tenants/default/pending_review/fast/run/video.mp4",
      video_url: "tenants/default/pending_review/fast/run/video.mp4",
      filename: "video.mp4",
      llm_prompt: "prompt",
      scene_description: "scene",
      user_prompt: "prompt",
      duration_seconds: 10,
      file_size_bytes: 1024,
      generation_time_ms: 10,
      timing: { llm_ms: 1, video_ms: 9, tts_ms: 0 },
      model_info: { llm: "fake", video: "fake", tts: null },
      is_stub: false,
      tts_path: null,
    });
    const { container, cleanup } = await renderFastModePanel();
    const textarea = container.querySelector("textarea");
    const generateButton = container.querySelector("button.apple-btn-primary");
    expect(textarea).toBeTruthy();
    expect(generateButton).toBeTruthy();

    await act(async () => {
      const valueSetter = Object.getOwnPropertyDescriptor(
        HTMLTextAreaElement.prototype,
        "value",
      )?.set;
      valueSetter?.call(textarea, "safe object shot");
      textarea?.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => {
      generateButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(container.textContent).toContain("有界完成");
    expect(container.textContent).not.toContain("生成失败");
    expect(container.querySelector('[data-testid="runtime-video"]')).toBeTruthy();
    cleanup();
  });
});
