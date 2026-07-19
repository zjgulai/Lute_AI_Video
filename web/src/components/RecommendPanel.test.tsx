import { act } from "react";
import { createRoot } from "react-dom/client";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n/I18nProvider";
import RecommendPanel, { buildLocalRecommendation } from "./RecommendPanel";
import { runS1Step, startS1StepByStep } from "./api";

vi.mock("./api", () => ({
  isDemoMode: vi.fn(() => false),
  startS1StepByStep: vi.fn(),
  runS1Step: vi.fn(),
}));

vi.mock("./DurationSlider", () => ({
  default: ({ value }: { value: number }) => <div data-duration={value}>duration</div>,
}));

async function renderRecommendPanel(props: React.ComponentProps<typeof RecommendPanel>) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(
      <I18nProvider>
        <RecommendPanel {...props} />
      </I18nProvider>,
    );
  });
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 30));
  });
  return {
    container,
    cleanup: () => {
      act(() => root.unmount());
      document.body.removeChild(container);
    },
  };
}

describe("RecommendPanel scenario mode boundaries", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("builds local recommendations for non-S1 scenarios", () => {
    expect(
      buildLocalRecommendation({
        content_scenario: "brand_campaign",
        key_message: "Launch a calmer care routine",
        target_platforms: ["tiktok"],
        video_duration: 45,
        brand_guidelines: {
          tone_of_voice: {
            keywords: ["warm", "supportive"],
          },
        },
      }),
    ).toEqual({
      summary: "Launch a calmer care routine",
      tone: "warm, supportive",
      platforms: ["tiktok"],
      duration: 45,
    });
  });

  it("does not call S1 step-by-step recommendation API for non-S1 scenarios", async () => {
    const { container, cleanup } = await renderRecommendPanel({
      config: {
        content_scenario: "brand_campaign",
        key_message: "Launch a calmer care routine",
        target_platforms: ["tiktok"],
        video_duration: 30,
      },
      onBack: vi.fn(),
      onStart: vi.fn(),
    });

    expect(startS1StepByStep).not.toHaveBeenCalled();
    expect(container.textContent).toContain("Launch a calmer care routine");
    expect(container.textContent).toContain("Step-by-step");
    cleanup();
  });

  it("keeps S1 recommendation rendering provider-free", async () => {
    const { container, cleanup } = await renderRecommendPanel({
      config: {
        content_scenario: "product_direct",
        product_catalog: { products: [{ name: "Momcozy M9" }] },
        target_platforms: ["tiktok"],
        video_duration: 30,
      },
      onBack: vi.fn(),
      onStart: vi.fn(),
    });

    expect(startS1StepByStep).not.toHaveBeenCalled();
    expect(runS1Step).not.toHaveBeenCalled();
    expect(container.textContent).toContain("Momcozy M9");
    cleanup();
  });

  it("keeps generation behind one explicit Start action", async () => {
    const onStart = vi.fn();
    const { container, cleanup } = await renderRecommendPanel({
      config: {
        content_scenario: "product_direct",
        product_catalog: { products: [{ name: "Momcozy M9" }] },
        target_platforms: ["tiktok"],
        video_duration: 30,
      },
      onBack: vi.fn(),
      onStart,
    });
    const buttons = Array.from(container.querySelectorAll("button"));
    const startButton = buttons.at(-1);
    expect(startButton).toBeTruthy();

    await act(async () => {
      startButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      startButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    expect(startS1StepByStep).not.toHaveBeenCalled();
    expect(runS1Step).not.toHaveBeenCalled();
    expect(onStart).toHaveBeenCalledTimes(1);
    cleanup();
  });
});
