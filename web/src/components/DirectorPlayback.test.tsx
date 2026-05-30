import { describe, expect, it } from "vitest";
import { act } from "react";
import { createRoot } from "react-dom/client";

import { I18nProvider } from "@/i18n/I18nProvider";
import DirectorPlayback from "./DirectorPlayback";

function renderDirectorPlayback(props: React.ComponentProps<typeof DirectorPlayback>) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(
      <I18nProvider>
        <DirectorPlayback {...props} />
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

describe("DirectorPlayback continuity diagnostics", () => {
  it("renders tooltip-backed transition intent for long continuity text", () => {
    const longTransitionIntent =
      "bridge setup into product interaction with extended pacing control and closing recall emphasis for approval";

    const { container, cleanup } = renderDirectorPlayback({
      result: {
        final_video_path: "/tmp/final.mp4",
        audit_report: {
          overall_status: "PASS",
          overall_score: 0.91,
          summary: "quality ready",
          criteria: [],
          continuity_score: 0.83,
          asset_ready_audit: {
            status: "PASS",
            checks: {
              director_intent_metadata: true,
            },
          },
          continuity_direction_summary: {
            clip_directions: [
              {
                scene_beat: "context_setup",
                transition_intent: longTransitionIntent,
              },
            ],
            scene_beats: ["context_setup"],
            transition_intents: [longTransitionIntent],
          },
        },
      },
      scenario: "product_direct",
    });

    const qualityToggle = Array.from(container.querySelectorAll("button")).find((node) =>
      (node.textContent || "").includes("Quality Report"),
    ) as HTMLButtonElement | undefined;

    expect(qualityToggle).toBeTruthy();
    act(() => {
      qualityToggle?.click();
    });

    const trigger = container.querySelector(
      `[aria-label*="${longTransitionIntent.slice(0, 24)}"]`,
    ) as HTMLElement | null;
    const tooltip = container.querySelector("[role='tooltip']") as HTMLElement | null;

    expect(container.textContent).toContain("Director intent diagnostics");
    expect(trigger).not.toBeNull();
    expect(trigger?.textContent).toContain("…");
    expect(tooltip?.textContent).toContain(longTransitionIntent);
    cleanup();
  });
});
