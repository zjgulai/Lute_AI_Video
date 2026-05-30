import { describe, expect, it } from "vitest";
import { act } from "react";
import { createRoot } from "react-dom/client";

import { I18nProvider } from "@/i18n/I18nProvider";
import QualityDashboard from "./QualityDashboard";
import type { AuditReport } from "./types";

function renderQualityDashboard(props: React.ComponentProps<typeof QualityDashboard>) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(
      <I18nProvider>
        <QualityDashboard {...props} />
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

describe("QualityDashboard continuity diagnostics", () => {
  it("renders tooltip-backed transition intent for long continuity text", () => {
    const longTransitionIntent =
      "bridge setup into product interaction with extended pacing control and closing recall emphasis for approval";
    const qualityReport: AuditReport & Record<string, unknown> = {
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
    };

    const { container, cleanup } = renderQualityDashboard({
      qualityReport,
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
