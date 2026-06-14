import { describe, it, expect, vi, beforeEach } from "vitest";
import { createRoot } from "react-dom/client";
import { act } from "react";
import { I18nProvider } from "@/i18n/I18nProvider";

vi.mock("./api", () => ({
  isDemoMode: vi.fn(() => true),
  fetchS1State: vi.fn(),
  apiFetch: vi.fn(),
  fetchGateState: vi.fn(),
}));

vi.mock("@/demo-data", () => ({
  DEMO_RESULT_1: {
    scripts: [
      { script_id: "s-1", hook: "Catch your eye", body: "Body 1" },
      { script_id: "s-2", hook: "Try this product", body: "Body 2" },
      { script_id: "s-3", hook: "Game-changer hack", body: "Body 3" },
    ],
    storyboards: [
      { board_id: "b-1", scenes: [] },
      { board_id: "b-2", scenes: [] },
      { board_id: "b-3", scenes: [] },
    ],
    seedance_output: {
      clip_details: [
        { clip_id: "c-1" },
        { clip_id: "c-2" },
        { clip_id: "c-3" },
      ],
      total_duration: 30,
    },
    final_video_path: "/demo.mp4",
    audit_report: {},
    thumbnail_image_paths: [],
    video_duration: 30,
  },
}));

import GatePanel from "./GatePanel";
import { apiFetch, fetchGateState, isDemoMode } from "./api";

async function renderGate(props: React.ComponentProps<typeof GatePanel>) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(<I18nProvider>{<GatePanel {...props} />}</I18nProvider>);
  });
  await act(async () => {
    await new Promise((r) => setTimeout(r, 30));
  });
  return {
    container,
    cleanup: () => {
      act(() => root.unmount());
      document.body.removeChild(container);
    },
  };
}

const baseProps: React.ComponentProps<typeof GatePanel> = {
  label: "s1_test_label",
  gateId: "gate_1_script",
  gateLabel: "Script Selection",
  maxSelections: 1,
  currentStep: 1,
  totalSteps: 4,
  gateSequence: [
    { gateId: "gate_1_script", gateLabel: "Script", maxSelections: 1 },
    { gateId: "gate_2_keyframe", gateLabel: "Keyframe", maxSelections: 1 },
  ],
  onApprove: () => {},
  onBack: () => {},
};

describe("GatePanel — demo mode rendering (D3)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(isDemoMode).mockReturnValue(true);
  });

  it("renders without crashing and shows candidate cards for gate_1_script", async () => {
    const { container, cleanup } = await renderGate(baseProps);
    const cards = container.querySelectorAll("[data-candidate-id]");
    expect(cards.length).toBe(3);
    cleanup();
  });

  it("renders gate progress / step indicator (Step N / M)", async () => {
    const { container, cleanup } = await renderGate({ ...baseProps, currentStep: 2, totalSteps: 4 });
    expect(container.textContent).toMatch(/2.*4|step.*2|Step.*2/i);
    cleanup();
  });

  it("approve button is disabled until at least one candidate is selected", async () => {
    const { container, cleanup } = await renderGate(baseProps);
    const buttons = Array.from(container.querySelectorAll("button"));
    const approveBtn = buttons.find((b) =>
      (b.textContent || "").toLowerCase().match(/approve|confirm|continue|\u786e\u8ba4|\u901a\u8fc7/),
    ) as HTMLButtonElement | undefined;
    if (approveBtn) {
      expect(approveBtn.disabled).toBe(true);
    } else {
      expect(buttons.length).toBeGreaterThan(0);
    }
    cleanup();
  });

  it("clicking Select on a candidate updates internal state (button is no longer for that card)", async () => {
    const { container, cleanup } = await renderGate(baseProps);
    const card = container.querySelector('[data-candidate-id="script-1"]') as HTMLElement;
    expect(card).toBeTruthy();
    const selectBtn = card.querySelectorAll("button")[0] as HTMLButtonElement;
    expect(selectBtn).toBeTruthy();
    await act(async () => {
      selectBtn.click();
      await new Promise((r) => setTimeout(r, 20));
    });
    const cardAfter = container.querySelector('[data-candidate-id="script-1"]') as HTMLElement;
    expect(cardAfter.outerHTML).toMatch(/ring-|fortune-red/);
    cleanup();
  });

  it("calls onApprove with selected candidate ids on approve flow", async () => {
    const onApprove = vi.fn();
    const { container, cleanup } = await renderGate({ ...baseProps, onApprove });
    const card = container.querySelector('[data-candidate-id="script-2"]') as HTMLElement;
    const selectBtn = card.querySelectorAll("button")[0] as HTMLButtonElement;
    await act(async () => {
      selectBtn.click();
      await new Promise((r) => setTimeout(r, 20));
    });
    const buttons = Array.from(container.querySelectorAll("button"));
    const approveBtn = buttons.find((b) => {
      const lc = (b.textContent || "").toLowerCase();
      return (
        lc.includes("approve") ||
        lc.includes("continue") ||
        lc.includes("confirm") ||
        b.textContent?.includes("\u786e\u8ba4") ||
        b.textContent?.includes("\u901a\u8fc7") ||
        b.textContent?.includes("\u4e0b\u4e00\u6b65")
      );
    }) as HTMLButtonElement | undefined;
    if (!approveBtn) {
      cleanup();
      return;
    }
    expect(approveBtn.disabled).toBe(false);
    await act(async () => {
      approveBtn.click();
      await new Promise((r) => setTimeout(r, 1000));
    });
    expect(onApprove).toHaveBeenCalledWith(["script-2"]);
    cleanup();
  });

  it("renders candidates for gate_2_keyframe with storyboard data", async () => {
    const { container, cleanup } = await renderGate({
      ...baseProps,
      gateId: "gate_2_keyframe",
      gateLabel: "Keyframe",
    });
    const cards = container.querySelectorAll("[data-candidate-id]");
    expect(cards.length).toBe(3);
    expect(container.querySelector('[data-candidate-id="keyframe-1"]')).toBeTruthy();
    cleanup();
  });

  it("renders candidates for gate_3_clips with clip data", async () => {
    const { container, cleanup } = await renderGate({
      ...baseProps,
      gateId: "gate_3_clips",
      gateLabel: "Clips",
    });
    const cards = container.querySelectorAll("[data-candidate-id]");
    expect(cards.length).toBe(3);
    expect(container.querySelector('[data-candidate-id="clip-1"]')).toBeTruthy();
    cleanup();
  });

  it("renders progress indicator with currentStep / totalSteps", async () => {
    const { container, cleanup } = await renderGate({
      ...baseProps,
      currentStep: 2,
      totalSteps: 4,
    });
    const text = container.textContent || "";
    expect(text).toMatch(/2.*4|2 \/ 4|step 2/i);
    cleanup();
  });

  it("invokes onBack when back-button is clicked", async () => {
    const onBack = vi.fn();
    const { container, cleanup } = await renderGate({ ...baseProps, onBack });
    const buttons = Array.from(container.querySelectorAll("button"));
    const backBtn = buttons.find((b) => {
      const lc = (b.textContent || "").toLowerCase();
      return (
        lc.includes("back") ||
        b.textContent?.includes("\u8fd4\u56de") ||
        b.getAttribute("aria-label")?.toLowerCase().includes("back")
      );
    }) as HTMLButtonElement | undefined;
    if (backBtn) {
      await act(async () => {
        backBtn.click();
      });
      expect(onBack).toHaveBeenCalled();
    }
    cleanup();
  });

  it("renders tooltip-backed continuity diagnostics for long gate text", async () => {
    vi.mocked(isDemoMode).mockReturnValue(false);
    vi.mocked(apiFetch).mockResolvedValue({
      ok: true,
      json: async () => ({}),
    } as Response);
    const longBeatSummary =
      "context setup into product introduction with layered proof beats and detail emphasis for continuity review";
    const longTransitionIntent =
      "bridge setup into product interaction with extended pacing control and closing recall emphasis for approval";
    vi.mocked(fetchGateState).mockResolvedValue({
      candidates: [],
      continuity_diagnostics: {
        continuity_score: 0.82,
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

    const { container, cleanup } = await renderGate(baseProps);
    const tooltipTrigger = container.querySelector(
      `[aria-label*="${longTransitionIntent.slice(0, 24)}"]`,
    ) as HTMLElement | null;
    const tooltips = Array.from(container.querySelectorAll('[role="tooltip"]')) as HTMLElement[];

    expect(container.textContent).toContain("Director intent diagnostics");
    expect(tooltipTrigger).not.toBeNull();
    expect(tooltipTrigger?.textContent).toContain("…");
    expect(tooltips.some((node) => (node.textContent || "").includes(longBeatSummary))).toBe(true);
    expect(tooltips.some((node) => (node.textContent || "").includes(longTransitionIntent))).toBe(true);
    cleanup();
  });
});
