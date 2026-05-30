export interface ContinuityClipDirection {
  scene_beat?: string;
  beat_summary?: string;
  transition_intent?: string;
}

export interface ContinuityDiagnosticsPayload {
  continuity_score?: number | null;
  asset_ready_status?: string | null;
  director_intent_metadata?: boolean | null;
  clip_directions?: ContinuityClipDirection[];
  scene_beats?: string[];
  transition_intents?: string[];
}

export interface ContinuityDiagnosticsViewModel {
  continuityScore: number | null;
  assetReadyStatus: string;
  directorIntentMetadata: boolean | null;
  clipDirections: Array<{
    sceneBeat: string;
    beatSummary: string;
    transitionIntent: string;
  }>;
  sceneBeats: string[];
  transitionIntents: string[];
}

type Translate = (key: string, fallback?: string) => string;

export function normalizeContinuityDiagnostics(
  payload: ContinuityDiagnosticsPayload | null | undefined,
): ContinuityDiagnosticsViewModel {
  const clipDirections = Array.isArray(payload?.clip_directions)
    ? payload.clip_directions
        .filter((entry): entry is ContinuityClipDirection => Boolean(entry && typeof entry === "object"))
        .map((entry) => ({
          sceneBeat: String(entry.scene_beat || "").trim(),
          beatSummary: String(entry.beat_summary || "").trim(),
          transitionIntent: String(entry.transition_intent || "").trim(),
        }))
        .filter((entry) => entry.sceneBeat || entry.beatSummary || entry.transitionIntent)
    : [];

  return {
    continuityScore:
      typeof payload?.continuity_score === "number" ? payload.continuity_score : null,
    assetReadyStatus:
      typeof payload?.asset_ready_status === "string" ? payload.asset_ready_status : "",
    directorIntentMetadata:
      typeof payload?.director_intent_metadata === "boolean"
        ? payload.director_intent_metadata
        : null,
    clipDirections,
    sceneBeats: Array.isArray(payload?.scene_beats)
      ? payload.scene_beats.map((value) => String(value || "").trim()).filter(Boolean)
      : [],
    transitionIntents: Array.isArray(payload?.transition_intents)
      ? payload.transition_intents.map((value) => String(value || "").trim()).filter(Boolean)
      : [],
  };
}

export function hasContinuityDiagnostics(
  payload:
    | ContinuityDiagnosticsPayload
    | ContinuityDiagnosticsViewModel
    | null
    | undefined,
): boolean {
  const normalized =
    payload && "clipDirections" in payload
      ? (payload as ContinuityDiagnosticsViewModel)
      : normalizeContinuityDiagnostics(payload as ContinuityDiagnosticsPayload | null | undefined);
  return (
    normalized.continuityScore !== null ||
    normalized.directorIntentMetadata !== null ||
    normalized.clipDirections.length > 0
  );
}

export function getContinuityDiagnosticsSummary(
  payload: ContinuityDiagnosticsPayload | ContinuityDiagnosticsViewModel | null | undefined,
  t: Translate,
): string {
  const normalized =
    payload && "clipDirections" in payload
      ? (payload as ContinuityDiagnosticsViewModel)
      : normalizeContinuityDiagnostics(payload as ContinuityDiagnosticsPayload | null | undefined);

  const segments: string[] = [];
  if (normalized.directorIntentMetadata !== null) {
    segments.push(
      normalized.directorIntentMetadata
        ? t("continuity.directorIntentReady")
        : t("continuity.directorIntentMissing"),
    );
  }
  if (normalized.continuityScore !== null) {
    segments.push(
      `${t("continuity.scoreLabel")} ${Math.round(normalized.continuityScore * 100)}%`,
    );
  }
  return segments.join(" · ");
}

export function extractContinuityDiagnosticsFromAuditReport(
  auditReport: Record<string, unknown> | null | undefined,
): ContinuityDiagnosticsPayload {
  if (!auditReport || typeof auditReport !== "object") return {};

  const assetReadyAudit =
    auditReport.asset_ready_audit && typeof auditReport.asset_ready_audit === "object"
      ? (auditReport.asset_ready_audit as Record<string, unknown>)
      : {};
  const checks =
    assetReadyAudit.checks && typeof assetReadyAudit.checks === "object"
      ? (assetReadyAudit.checks as Record<string, unknown>)
      : {};
  const directionSummary =
    auditReport.continuity_direction_summary &&
    typeof auditReport.continuity_direction_summary === "object"
      ? (auditReport.continuity_direction_summary as Record<string, unknown>)
      : {};

  return {
    continuity_score:
      typeof auditReport.continuity_score === "number" ? auditReport.continuity_score : null,
    asset_ready_status:
      typeof assetReadyAudit.status === "string" ? assetReadyAudit.status : null,
    director_intent_metadata:
      typeof checks.director_intent_metadata === "boolean"
        ? checks.director_intent_metadata
        : null,
    clip_directions: Array.isArray(directionSummary.clip_directions)
      ? (directionSummary.clip_directions as ContinuityClipDirection[])
      : [],
    scene_beats: Array.isArray(directionSummary.scene_beats)
      ? (directionSummary.scene_beats as string[])
      : [],
    transition_intents: Array.isArray(directionSummary.transition_intents)
      ? (directionSummary.transition_intents as string[])
      : [],
  };
}
