/** Direction extracted from continuity/storyboard metadata. */
export interface ContinuityDirection {
  sceneBeat: string;
  beatSummary: string;
  transitionIntent: string;
}

type DirectionMetadata = Partial<ContinuityDirection> & {
  scene_beat?: string;
  beat_summary?: string;
  transition_intent?: string;
  [key: string]: unknown;
};

/** Structured metadata fields expected in a gate candidate's output. */
interface CandidateMetadata {
  clip_details?: DirectionMetadata[];
  clip_directions?: DirectionMetadata[];
  continuity_direction_summary?: {
    clip_directions?: DirectionMetadata[];
  };
  audit_report?: {
    continuity_direction_summary?: {
      clip_directions?: DirectionMetadata[];
    };
  };
  scene_beat?: string;
  beat_summary?: string;
  transition_intent?: string;
  [key: string]: unknown;
}

export function truncatePreview(data: unknown): string {
  if (!data) return "";
  if (typeof data === "string") return data.slice(0, 100);
  return JSON.stringify(data, null, 2).slice(0, 100);
}

export function extractContinuityDirections(data: unknown): ContinuityDirection[] {
  if (!data || typeof data !== "object") return [];

  const meta = data as CandidateMetadata;
  const candidates: DirectionMetadata[][] = [];

  if (Array.isArray(meta.clip_details)) candidates.push(meta.clip_details);
  if (Array.isArray(meta.clip_directions)) candidates.push(meta.clip_directions);

  if (meta.continuity_direction_summary && typeof meta.continuity_direction_summary === "object") {
    if (Array.isArray(meta.continuity_direction_summary.clip_directions)) {
      candidates.push(meta.continuity_direction_summary.clip_directions);
    }
  }

  if (meta.audit_report && typeof meta.audit_report === "object") {
    const auditContinuity = meta.audit_report.continuity_direction_summary;
    if (auditContinuity && typeof auditContinuity === "object") {
      if (Array.isArray(auditContinuity.clip_directions)) {
        candidates.push(auditContinuity.clip_directions);
      }
    }
  }

  if (typeof meta.scene_beat === "string" || typeof meta.beat_summary === "string" || typeof meta.transition_intent === "string") {
    candidates.push([meta]);
  }

  for (const candidate of candidates) {
    if (!Array.isArray(candidate)) continue;
    const normalized = candidate
      .filter((entry): entry is DirectionMetadata => Boolean(entry && typeof entry === "object"))
      .map((entry) => ({
        sceneBeat: String(entry.sceneBeat || entry.scene_beat || "").trim(),
        beatSummary: String(entry.beatSummary || entry.beat_summary || "").trim(),
        transitionIntent: String(entry.transitionIntent || entry.transition_intent || "").trim(),
      }))
      .filter((d) => d.sceneBeat || d.beatSummary || d.transitionIntent);
    if (normalized.length > 0) return normalized;
  }

  return [];
}
