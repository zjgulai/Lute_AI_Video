import { describe, expect, it } from "vitest";

import {
  extractContinuityDiagnosticsFromAuditReport,
  getContinuityDiagnosticsSummary,
  hasContinuityDiagnostics,
  normalizeContinuityDiagnostics,
} from "./continuityDiagnostics";

const dictionary: Record<string, string> = {
  "continuity.directorIntentReady": "导演意图元数据完整",
  "continuity.directorIntentMissing": "导演意图元数据缺失",
  "continuity.scoreLabel": "连贯性得分",
};

const t = (key: string, fallback?: string): string => dictionary[key] ?? fallback ?? key;

describe("continuity diagnostics helpers", () => {
  it("normalizes structured clip directions", () => {
    const result = normalizeContinuityDiagnostics({
      continuity_score: 0.8,
      asset_ready_status: "PASS",
      director_intent_metadata: true,
      clip_directions: [
        {
          scene_beat: "context_setup",
          beat_summary: "context_setup -> product_intro",
          transition_intent: "bridge setup into product interaction",
        },
      ],
      scene_beats: ["context_setup"],
      transition_intents: ["bridge setup into product interaction"],
    });

    expect(result.continuityScore).toBe(0.8);
    expect(result.assetReadyStatus).toBe("PASS");
    expect(result.directorIntentMetadata).toBe(true);
    expect(result.clipDirections[0]).toEqual({
      sceneBeat: "context_setup",
      beatSummary: "context_setup -> product_intro",
      transitionIntent: "bridge setup into product interaction",
    });
  });

  it("detects empty diagnostics", () => {
    expect(hasContinuityDiagnostics(undefined)).toBe(false);
    expect(hasContinuityDiagnostics({})).toBe(false);
  });

  it("detects non-empty diagnostics", () => {
    expect(hasContinuityDiagnostics({ director_intent_metadata: false })).toBe(true);
  });

  it("detects non-empty normalized diagnostics", () => {
    expect(
      hasContinuityDiagnostics({
        continuityScore: 0.8,
        assetReadyStatus: "PASS",
        directorIntentMetadata: true,
        clipDirections: [],
        sceneBeats: [],
        transitionIntents: [],
      }),
    ).toBe(true);
  });

  it("formats summary with director intent before score", () => {
    expect(
      getContinuityDiagnosticsSummary(
        {
          continuity_score: 0.8,
          director_intent_metadata: true,
        },
        t,
      ),
    ).toBe("导演意图元数据完整 · 连贯性得分 80%");
  });

  it("extracts continuity diagnostics from audit report shape", () => {
    const result = extractContinuityDiagnosticsFromAuditReport({
      continuity_score: 0.85,
      asset_ready_audit: {
        status: "PASS",
        checks: { director_intent_metadata: true },
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
    });

    expect(result.continuity_score).toBe(0.85);
    expect(result.asset_ready_status).toBe("PASS");
    expect(result.director_intent_metadata).toBe(true);
    expect(result.clip_directions?.[0]).toEqual({
      scene_beat: "context_setup",
      beat_summary: "context_setup -> product_intro",
      transition_intent: "bridge setup into product interaction",
    });
  });
});
