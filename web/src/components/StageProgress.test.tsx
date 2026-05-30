import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { act } from "react";
import { createRoot } from "react-dom/client";

import { I18nProvider } from "@/i18n/I18nProvider";
import StageProgress, { deriveStageRuntimeState, deriveTotalProgress, estimateRemainingSeconds } from "./StageProgress";
import { getScenarioStatus } from "./api";

vi.mock("./api", () => ({
  getScenarioStatus: vi.fn(),
}));

function renderStageProgress(props: React.ComponentProps<typeof StageProgress>) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(
      <I18nProvider>
        <StageProgress {...props} />
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

describe("StageProgress continuity diagnostics", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("derives stage progress and active stage from step statuses", () => {
    const stageDefs = [
      {
        id: "writing",
        label: "stage.writing",
        narrative: "exec.narrative.analyzing",
        steps: ["strategy", "scripts"],
        estimatedSeconds: 10,
      },
      {
        id: "visuals",
        label: "stage.visuals",
        narrative: "exec.narrative.visualizing",
        steps: ["storyboards", "video_prompts"],
        estimatedSeconds: 20,
      },
    ];

    const partialState = deriveStageRuntimeState(stageDefs, {
      strategy: { status: "done" },
      scripts: { status: "done" },
      storyboards: { status: "running" },
    });

    expect(partialState.activeStageIdx).toBe(1);
    expect(partialState.allComplete).toBe(false);
    expect(partialState.stageCompletionKey).toBe("1,0");
    expect(partialState.stageStates.map((stage) => stage.progress)).toEqual([100, 0]);
    expect(partialState.stageStates.map((stage) => stage.anyStarted)).toEqual([true, true]);

    const completeState = deriveStageRuntimeState(stageDefs, {
      strategy: { status: "done" },
      scripts: { status: "done" },
      storyboards: { status: "done" },
      video_prompts: { status: "done" },
    });

    expect(completeState.activeStageIdx).toBe(1);
    expect(completeState.allComplete).toBe(true);
    expect(completeState.stageCompletionKey).toBe("1,1");
  });

  it("estimates remaining seconds from elapsed pace and step durations", () => {
    const stageDefs = [
      {
        id: "writing",
        label: "stage.writing",
        narrative: "exec.narrative.analyzing",
        steps: ["strategy", "scripts"],
        estimatedSeconds: 20,
      },
      {
        id: "visuals",
        label: "stage.visuals",
        narrative: "exec.narrative.visualizing",
        steps: ["storyboards", "video_prompts"],
        estimatedSeconds: 40,
      },
    ];

    expect(
      estimateRemainingSeconds({
        allComplete: false,
        elapsed: 4,
        stageDefs,
        steps: { strategy: { status: "done", duration_ms: 10000 } },
      }),
    ).toBeNull();

    expect(
      estimateRemainingSeconds({
        allComplete: true,
        elapsed: 30,
        stageDefs,
        steps: {},
      }),
    ).toBe(0);

    expect(
      estimateRemainingSeconds({
        allComplete: false,
        elapsed: 20,
        stageDefs,
        steps: {
          strategy: { status: "done", duration_ms: 10000 },
          scripts: { status: "running" },
          storyboards: { status: "done", duration_ms: 30000 },
          video_prompts: { status: "pending" },
        },
      }),
    ).toBe(20);
  });

  it("derives total progress from done steps across stages", () => {
    const stageDefs = [
      {
        id: "writing",
        label: "stage.writing",
        narrative: "exec.narrative.analyzing",
        steps: ["strategy", "scripts"],
        estimatedSeconds: 20,
      },
      {
        id: "visuals",
        label: "stage.visuals",
        narrative: "exec.narrative.visualizing",
        steps: ["storyboards", "video_prompts"],
        estimatedSeconds: 40,
      },
    ];

    expect(
      deriveTotalProgress(stageDefs, {
        strategy: { status: "done" },
        scripts: { status: "running" },
        storyboards: { status: "done" },
      }),
    ).toEqual({
      totalSteps: 4,
      totalDone: 2,
      totalProgress: 50,
    });

    expect(deriveTotalProgress([], {})).toEqual({
      totalSteps: 0,
      totalDone: 0,
      totalProgress: 0,
    });
  });

  it("clears the initial polling timer when unmounted before the first status request", async () => {
    vi.mocked(getScenarioStatus).mockResolvedValue({
      status: "running",
      steps: {},
      errors: [],
      soft_degraded_reasons: [],
      continuity_diagnostics: null,
    } as never);

    const { cleanup } = renderStageProgress({
      label: "s1_unmount_before_poll",
      scenario: "s1",
      onComplete: () => {},
    });

    cleanup();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });

    expect(getScenarioStatus).not.toHaveBeenCalled();
  });

  it("renders tooltip-backed continuity diagnostics for long running-stage text", async () => {
    const longBeatSummary =
      "context setup into product introduction with layered proof beats and detail emphasis for continuity review";
    const longTransitionIntent =
      "bridge setup into product interaction with extended pacing control and closing recall emphasis for approval";

    vi.mocked(getScenarioStatus).mockResolvedValue({
      status: "running",
      steps: {
        strategy: { status: "done", duration_ms: 1000 },
      },
      errors: [],
      soft_degraded_reasons: [],
      continuity_diagnostics: {
        continuity_score: 0.81,
        director_intent_metadata: true,
        clip_directions: [
          {
            scene_beat: "context_setup",
            beat_summary: longBeatSummary,
            transition_intent: longTransitionIntent,
          },
        ],
      },
    } as never);

    const { container, cleanup } = renderStageProgress({
      label: "s1_test_label",
      scenario: "s1",
      onComplete: () => {},
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2200);
    });

    const trigger = container.querySelector(
      `[aria-label*="${longTransitionIntent.slice(0, 24)}"]`,
    ) as HTMLElement | null;
    const tooltips = Array.from(container.querySelectorAll("[role='tooltip']")) as HTMLElement[];

    expect(container.textContent).toContain("Director intent diagnostics");
    expect(trigger).not.toBeNull();
    expect(trigger?.textContent).toContain("…");
    expect(tooltips.some((node) => (node.textContent || "").includes(longBeatSummary))).toBe(true);
    expect(tooltips.some((node) => (node.textContent || "").includes(longTransitionIntent))).toBe(true);
    cleanup();
  });

  it("does not call onComplete after unmounting during delayed completion", async () => {
    const onComplete = vi.fn();

    vi.mocked(getScenarioStatus).mockResolvedValue({
      status: "completed",
      steps: {
        strategy: { status: "done" },
        scripts: { status: "done" },
        compliance: { status: "done" },
        storyboards: { status: "done" },
        keyframe_images: { status: "done" },
        video_prompts: { status: "done" },
        thumbnail_prompts: { status: "done" },
        seedance_clips: { status: "done" },
        tts_audio: { status: "done" },
        thumbnail_images: { status: "done" },
        assemble_final: { status: "done" },
        audit: { status: "done" },
      },
      result: { output: "ok" },
      errors: [],
      soft_degraded_reasons: [],
      continuity_diagnostics: null,
    } as never);

    const { cleanup } = renderStageProgress({
      label: "s1_complete_label",
      scenario: "s1",
      onComplete,
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2200);
    });

    cleanup();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    expect(onComplete).not.toHaveBeenCalled();
  });

  it("stops polling after repeated status failures reach the threshold", async () => {
    vi.mocked(getScenarioStatus).mockRejectedValue(new Error("network unavailable"));

    const { container, cleanup } = renderStageProgress({
      label: "s1_poll_failure_label",
      scenario: "s1",
      onComplete: () => {},
    });

    for (let index = 0; index < 10; index += 1) {
      await act(async () => {
        await vi.runOnlyPendingTimersAsync();
      });
    }

    const callCountAtThreshold = vi.mocked(getScenarioStatus).mock.calls.length;

    await act(async () => {
      await vi.advanceTimersByTimeAsync(120_000);
    });

    expect(callCountAtThreshold).toBe(10);
    expect(getScenarioStatus).toHaveBeenCalledTimes(callCountAtThreshold);
    expect(container.textContent).toContain("Connection lost. Please refresh to retry.");

    cleanup();
  });

  it("stops elapsed timer when the status response enters an error state", async () => {
    const onError = vi.fn();

    vi.mocked(getScenarioStatus).mockResolvedValue({
      status: "error",
      steps: {
        strategy: { status: "done" },
      },
      errors: ["render failed"],
      soft_degraded_reasons: [],
      continuity_diagnostics: null,
    } as never);

    const { container, cleanup } = renderStageProgress({
      label: "s1_error_label",
      scenario: "s1",
      onComplete: () => {},
      onError,
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2200);
    });

    expect(container.textContent).toContain("Elapsed: 00:02");
    expect(onError).toHaveBeenCalledTimes(1);
    expect(onError).toHaveBeenCalledWith(["render failed"]);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });

    expect(container.textContent).toContain("Elapsed: 00:02");
    expect(getScenarioStatus).toHaveBeenCalledTimes(1);
    expect(onError).toHaveBeenCalledTimes(1);

    cleanup();
  });

  it("deduplicates repeated gate pause notifications for the same current step", async () => {
    const onGatePause = vi.fn();

    vi.mocked(getScenarioStatus).mockResolvedValue({
      status: "paused",
      gate_status: "awaiting_approval",
      current_step: "gate_1_scripts",
      steps: {
        strategy: { status: "done" },
      },
      errors: [],
      soft_degraded_reasons: [],
      continuity_diagnostics: null,
    } as never);

    const { cleanup } = renderStageProgress({
      label: "s1_gate_pause_label",
      scenario: "s1",
      onComplete: () => {},
      onGatePause,
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2200);
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });

    expect(getScenarioStatus).toHaveBeenCalledTimes(2);
    expect(onGatePause).toHaveBeenCalledTimes(1);
    expect(onGatePause).toHaveBeenCalledWith("gate_1_scripts");

    cleanup();
  });

  it("keeps elapsed active but reduces polling cadence while waiting for gate approval", async () => {
    vi.mocked(getScenarioStatus).mockResolvedValue({
      status: "paused",
      gate_status: "awaiting_approval",
      current_step: "gate_1_scripts",
      steps: {
        strategy: { status: "done" },
      },
      errors: [],
      soft_degraded_reasons: [],
      continuity_diagnostics: null,
    } as never);

    const { container, cleanup } = renderStageProgress({
      label: "s1_gate_wait_label",
      scenario: "s1",
      onComplete: () => {},
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2200);
    });

    expect(container.textContent).toContain("Elapsed: 00:02");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000);
    });

    expect(container.textContent).toContain("Elapsed: 00:06");
    expect(getScenarioStatus).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });

    expect(container.textContent).toContain("Elapsed: 00:12");
    expect(getScenarioStatus).toHaveBeenCalledTimes(2);

    cleanup();
  });
});
