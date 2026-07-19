import { describe, expect, it } from "vitest";
import { createRoot } from "react-dom/client";
import { act } from "react";

import CompareView, { type Version } from "./CompareView";
import { I18nProvider } from "@/i18n/I18nProvider";
import type { AuditReport } from "./types";

function renderCompareView(props: React.ComponentProps<typeof CompareView>) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(
      <I18nProvider>
        <CompareView {...props} />
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

function makeVersion(overrides?: Partial<Version>): Version {
  return {
    label: "Version A",
    scriptVariant: "standard",
    videoPath: "/tmp/video-a.mp4",
    thumbnailPath: "/tmp/thumb-a.png",
    auditReport: null,
    duration: 15,
    fileSize: 1024,
    ...overrides,
  };
}

describe("CompareView continuity diagnostics", () => {
  it("renders continuity summary and first clip direction on version card", () => {
    const auditReport: AuditReport & Record<string, unknown> = {
      overall_status: "PASS",
      overall_score: 0.91,
      criteria: [],
      summary: "continuity ready",
      continuity_score: 0.82,
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
            beat_summary: "context_setup -> product_intro",
            transition_intent: "bridge setup into product interaction",
          },
        ],
        scene_beats: ["context_setup"],
        transition_intents: ["bridge setup into product interaction"],
      },
    };

    const version = makeVersion({
      auditReport,
    });

    const { container, cleanup } = renderCompareView({
      versions: [version],
      onSelect: () => {},
      onNewCreation: () => {},
      onBack: () => {},
      onPublish: async () => {},
      selectedVersion: null,
    });

    const text = container.textContent || "";
    expect(text).toContain("Director-intent metadata complete");
    expect(text).toContain("Continuity score 82%");
    cleanup();
  });

  it("renders selected-version continuity verdict in bottom action area", () => {
    const auditReport: AuditReport & Record<string, unknown> = {
      overall_status: "PASS",
      overall_score: 0.9,
      criteria: [],
      summary: "selected continuity ready",
      continuity_score: 0.76,
      asset_ready_audit: {
        status: "PASS",
        checks: {
          director_intent_metadata: true,
        },
      },
      continuity_direction_summary: {
        clip_directions: [
          {
            scene_beat: "product_intro",
            beat_summary: "product_intro -> proof",
            transition_intent: "tighten into proof sequence",
          },
        ],
        scene_beats: ["product_intro"],
        transition_intents: ["tighten into proof sequence"],
      },
    };

    const version = makeVersion({
      label: "Version B",
      auditReport,
    });

    const { container, cleanup } = renderCompareView({
      versions: [version],
      onSelect: () => {},
      onNewCreation: () => {},
      onBack: () => {},
      onPublish: async () => {},
      selectedVersion: "Version B",
    });

    const text = container.textContent || "";
    expect(text).toContain("Version B");
    expect(text).toContain("Director intent diagnostics");
    expect(text).toContain("Continuity score 76%");
    expect(text).toContain("product_intro");
    expect(text).toContain("tighten into proof sequence");
    cleanup();
  });

  it("renders continuity rows inside quality comparison table", () => {
    const versionA = makeVersion({
      label: "Version A",
      auditReport: {
        overall_status: "PASS",
        overall_score: 0.93,
        criteria: [{ name: "visual quality", score: 0.9, status: "PASS" }],
        summary: "a ready",
        continuity_score: 0.84,
        asset_ready_audit: {
          status: "PASS",
          checks: { director_intent_metadata: true },
        },
        continuity_direction_summary: {
          clip_directions: [
            {
              scene_beat: "context_setup",
              transition_intent: "bridge setup into product interaction",
            },
          ],
          scene_beats: ["context_setup"],
          transition_intents: ["bridge setup into product interaction"],
        },
      } as AuditReport & Record<string, unknown>,
    });
    const versionB = makeVersion({
      label: "Version B",
      auditReport: {
        overall_status: "WARN",
        overall_score: 0.72,
        criteria: [{ name: "visual quality", score: 0.7, status: "WARN" }],
        summary: "b ready",
        continuity_score: 0.61,
        asset_ready_audit: {
          status: "WARN",
          checks: { director_intent_metadata: false },
        },
        continuity_direction_summary: {
          clip_directions: [
            {
              scene_beat: "proof_sequence",
              transition_intent: "tighten into proof sequence",
            },
          ],
          scene_beats: ["proof_sequence"],
          transition_intents: ["tighten into proof sequence"],
        },
      } as AuditReport & Record<string, unknown>,
    });

    const { container, cleanup } = renderCompareView({
      versions: [versionA, versionB],
      onSelect: () => {},
      onNewCreation: () => {},
      onBack: () => {},
      onPublish: async () => {},
      selectedVersion: "Version A",
    });

    const text = container.textContent || "";
    expect(text).toContain("Continuity diagnostics");
    expect(text).toContain("Continuity summary");
    expect(text).toContain("Continuity verdict");
    expect(text).toContain("Quality criteria");
    expect(text).toContain("Director-intent metadata complete");
    expect(text).toContain("Director-intent metadata missing");
    expect(text).toContain("84%");
    expect(text).toContain("61%");
    expect(text).toContain("context_setup");
    expect(text).toContain("bridge setup into product interaction");
    expect(text).toContain("proof_sequence");
    expect(text).toContain("Transition intent: tig…");
    cleanup();
  });

  it("truncates long continuity verdict text in table while preserving full title", () => {
    const longIntent =
      "bridge setup into product interaction with extended proof sequencing, pacing control, tactile detail emphasis, and closing recall";
    const versionA = makeVersion({
      label: "Version A",
      auditReport: {
        overall_status: "PASS",
        overall_score: 0.93,
        criteria: [{ name: "visual quality", score: 0.9, status: "PASS" }],
        summary: "a ready",
        continuity_score: 0.84,
        asset_ready_audit: {
          status: "PASS",
          checks: { director_intent_metadata: true },
        },
        continuity_direction_summary: {
          clip_directions: [
            {
              scene_beat: "context_setup",
              transition_intent: longIntent,
            },
          ],
          scene_beats: ["context_setup"],
          transition_intents: [longIntent],
        },
      } as AuditReport & Record<string, unknown>,
    });
    const versionB = makeVersion({
      label: "Version B",
      auditReport: {
        overall_status: "PASS",
        overall_score: 0.9,
        criteria: [{ name: "visual quality", score: 0.88, status: "PASS" }],
        summary: "b ready",
        continuity_score: 0.82,
        asset_ready_audit: {
          status: "PASS",
          checks: { director_intent_metadata: true },
        },
        continuity_direction_summary: {
          clip_directions: [],
          scene_beats: [],
          transition_intents: [],
        },
      } as AuditReport & Record<string, unknown>,
    });

    const { container, cleanup } = renderCompareView({
      versions: [versionA, versionB],
      onSelect: () => {},
      onNewCreation: () => {},
      onBack: () => {},
      onPublish: async () => {},
      selectedVersion: "Version A",
    });

    const tooltipTrigger = container.querySelector(
      `[aria-label*="${longIntent.slice(0, 24)}"]`,
    ) as HTMLElement | null;
    const tooltip = container.querySelector('[role="tooltip"]') as HTMLElement | null;
    expect(tooltipTrigger).not.toBeNull();
    expect(tooltipTrigger?.getAttribute("title")).toBeNull();
    expect(tooltipTrigger?.getAttribute("aria-label")).toContain(longIntent);
    expect(tooltipTrigger?.textContent).toContain("…");
    expect(tooltip?.textContent).toContain(longIntent);
    cleanup();
  });
});
