"use client";

import { useMemo } from "react";
import { useI18n } from "@/i18n/I18nProvider";

interface Score {
  overall: number;
  breakdown?: Record<string, unknown>;
  explanation?: string;
}

export interface Candidate {
  id: string;
  variant: "standard" | "creative" | "conservative";
  data: unknown;
  score: Score;
  recommended: boolean;
}

interface Props {
  candidates: Candidate[];
  maxSelections: number;
  selectedIds: string[];
  onSelectionChange: (ids: string[]) => void;
  onEdit: (candidateId: string) => void;
}

function getScoreColor(score: number): string {
  if (score >= 0.8) return "bg-[var(--jade-accent)]";
  if (score >= 0.5) return "bg-[var(--gold-foil)]";
  return "bg-[var(--crimson-mist)]";
}

function getScoreBgColor(score: number): string {
  if (score >= 0.8) return "bg-[rgba(120,175,140,0.10)]";
  if (score >= 0.5) return "bg-[rgba(220,190,120,0.10)]";
  return "bg-[rgba(208,78,90,0.10)]";
}

function getScoreTextColor(score: number): string {
  if (score >= 0.8) return "text-[var(--jade-accent)]";
  if (score >= 0.5) return "text-[var(--gold-foil)]";
  return "text-[var(--crimson-mist)]";
}

function getVariantLabelKey(variant: string): string {
  switch (variant) {
    case "standard":
      return "gate.variant.standard";
    case "creative":
      return "gate.variant.creative";
    case "conservative":
      return "gate.variant.conservative";
    default:
      return variant;
  }
}

function getDataPreview(data: unknown): string {
  if (!data) return "";
  if (typeof data === "string") return data.slice(0, 100);
  const str = JSON.stringify(data, null, 2);
  return str.slice(0, 100);
}

function extractContinuityDirections(data: unknown): Array<{
  sceneBeat: string;
  beatSummary: string;
  transitionIntent: string;
}> {
  if (!data || typeof data !== "object") return [];

  const record = data as Record<string, unknown>;
  const candidates: unknown[] = [];

  if (Array.isArray(record.clip_details)) candidates.push(record.clip_details);
  if (Array.isArray(record.clip_directions)) candidates.push(record.clip_directions);

  const continuitySummary = record.continuity_direction_summary;
  if (continuitySummary && typeof continuitySummary === "object") {
    const summaryRecord = continuitySummary as Record<string, unknown>;
    if (Array.isArray(summaryRecord.clip_directions)) candidates.push(summaryRecord.clip_directions);
  }

  const auditReport = record.audit_report;
  if (auditReport && typeof auditReport === "object") {
    const auditRecord = auditReport as Record<string, unknown>;
    const auditSummary = auditRecord.continuity_direction_summary;
    if (auditSummary && typeof auditSummary === "object") {
      const summaryRecord = auditSummary as Record<string, unknown>;
      if (Array.isArray(summaryRecord.clip_directions)) candidates.push(summaryRecord.clip_directions);
    }
  }

  if (
    typeof record.scene_beat === "string" ||
    typeof record.beat_summary === "string" ||
    typeof record.transition_intent === "string"
  ) {
    candidates.push([record]);
  }

  for (const candidate of candidates) {
    if (!Array.isArray(candidate)) continue;
    const normalized = candidate
      .filter((entry): entry is Record<string, unknown> => Boolean(entry && typeof entry === "object"))
      .map((entry) => ({
        sceneBeat: String(entry.scene_beat || "").trim(),
        beatSummary: String(entry.beat_summary || "").trim(),
        transitionIntent: String(entry.transition_intent || "").trim(),
      }))
      .filter((entry) => entry.sceneBeat || entry.beatSummary || entry.transitionIntent);
    if (normalized.length > 0) return normalized;
  }

  return [];
}

function extractDirectorIntentScore(score: Score | undefined): number | null {
  const value = score?.breakdown?.director_intent;
  return typeof value === "number" ? value : null;
}

function prioritizeDirectorIntentExplanation(
  explanation: string | undefined,
  directorIntentScore: number | null,
): string {
  const text = String(explanation || "").trim();
  if (!text) return "";

  const colonIndex = text.indexOf(":");
  const prefix = colonIndex >= 0 ? text.slice(0, colonIndex + 1) : "";
  const body = colonIndex >= 0 ? text.slice(colonIndex + 1) : text;
  const segments = body
    .split(",")
    .map((segment) => segment.trim())
    .filter(Boolean);

  const directorIntentIndex = segments.findIndex((segment) =>
    segment.includes("director_intent="),
  );
  if (directorIntentIndex >= 0) {
    const prioritized = [
      segments[directorIntentIndex],
      ...segments.filter((_, index) => index !== directorIntentIndex),
    ].join(", ");
    return prefix ? `${prefix} ${prioritized}` : prioritized;
  }

  if (directorIntentScore !== null) {
    const directorIntentLead = `director_intent=${directorIntentScore.toFixed(2)}`;
    return prefix
      ? `${prefix} ${directorIntentLead}, ${segments.join(", ")}`
      : `${directorIntentLead}, ${segments.join(", ")}`;
  }

  return text;
}

function SkeletonCard() {
  return (
    <div className="flex-1 min-w-[200px] max-w-[260px] animate-pulse">
      <div className="apple-card p-4 space-y-3">
        {/* Variant badge skeleton */}
        <div className="flex justify-end">
          <div className="h-4 w-20 rounded-full bg-[rgba(215,92,112,0.18)]" />
        </div>
        {/* Score bar skeleton */}
        <div className="space-y-1">
          <div className="h-2 w-full rounded-full bg-[rgba(215,92,112,0.18)]" />
          <div className="h-3 w-12 rounded bg-[rgba(215,92,112,0.18)]" />
        </div>
        {/* Content preview skeleton */}
        <div className="space-y-1.5">
          <div className="h-2.5 w-full rounded bg-[rgba(215,92,112,0.18)]" />
          <div className="h-2.5 w-3/4 rounded bg-[rgba(215,92,112,0.18)]" />
          <div className="h-2.5 w-1/2 rounded bg-[rgba(215,92,112,0.18)]" />
        </div>
        {/* Button skeleton */}
        <div className="h-8 w-full rounded-lg bg-[rgba(215,92,112,0.18)]" />
        {/* Edit link skeleton */}
        <div className="h-3 w-12 mx-auto rounded bg-[rgba(215,92,112,0.18)]" />
      </div>
    </div>
  );
}

export default function CandidateSelector({
  candidates,
  maxSelections,
  selectedIds,
  onSelectionChange,
  onEdit,
}: Props) {
  const { t } = useI18n();

  const isAtMax = useMemo(
    () => selectedIds.length >= maxSelections,
    [selectedIds, maxSelections]
  );

  const handleToggle = (candidateId: string) => {
    const isSelected = selectedIds.includes(candidateId);
    if (isSelected) {
      onSelectionChange(selectedIds.filter((id) => id !== candidateId));
    } else if (isAtMax) {
      // Deselect the oldest selection to make room
      const [, ...rest] = selectedIds;
      onSelectionChange([...rest, candidateId]);
    } else {
      onSelectionChange([...selectedIds, candidateId]);
    }
  };

  // Empty/loading state: show skeleton placeholders
  if (!candidates || candidates.length === 0) {
    return (
      <div className="flex gap-3 justify-center">
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }

  return (
    <div className="flex gap-3 justify-center flex-wrap">
      {candidates.map((candidate) => {
        const isSelected = selectedIds.includes(candidate.id);
        const score = candidate.score?.overall ?? 0;
        const scorePct = Math.round(score * 100);
        const preview = getDataPreview(candidate.data);
        const continuityDirections = extractContinuityDirections(candidate.data);
        const directorIntentScore = extractDirectorIntentScore(candidate.score);
        const prioritizedExplanation = prioritizeDirectorIntentExplanation(
          candidate.score?.explanation,
          directorIntentScore,
        );

        let borderClass = "border-[rgba(215,92,112,0.18)]";
        if (isSelected) borderClass = "border-[var(--fortune-red)]";
        else if (candidate.recommended) borderClass = "border-[var(--fortune-red)]";

        return (
          <div
            key={candidate.id}
            data-candidate-id={candidate.id}
            className={`flex-1 min-w-[200px] max-w-[260px] apple-card p-4 border-2 transition-all relative ${
              isSelected ? "ring-2 ring-[rgba(215,92,112,0.20)]" : ""
            } ${borderClass}`}
          >
            {/* AI Recommended badge */}
            {candidate.recommended && (
              <div className="absolute -top-2.5 left-3">
                <span className="inline-flex items-center gap-1 text-[12px] font-semibold px-2 py-0.5 rounded-full bg-[var(--fortune-red)] text-white shadow-sm">
                  <svg width="10" height="10" viewBox="0 0 12 12" fill="none">
                    <path d="M6 1L7.5 4.5L11 5L8.5 7.5L9 11L6 9L3 11L3.5 7.5L1 5L4.5 4.5L6 1Z" fill="white" />
                  </svg>
                  {t("gate.aiRecommended")}
                </span>
              </div>
            )}

            {/* Selected checkmark */}
            {isSelected && (
              <div className="absolute -top-2.5 right-3">
                <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-[var(--fortune-red)] text-white shadow-sm">
                  <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                    <path d="M2 5.5L4 7.5L8 2.5" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </span>
              </div>
            )}

            {/* Variant badge */}
            <div className="flex justify-end mb-2">
              <span className={`text-[12px] font-semibold px-2 py-0.5 rounded-full ${getScoreBgColor(score)} ${getScoreTextColor(score)}`}>
                {t(getVariantLabelKey(candidate.variant))}
              </span>
            </div>

            {/* Score bar */}
            <div className="mb-2">
              <div className="flex items-center justify-between mb-1">
                <span className="text-[12px] text-[var(--text-muted)] font-medium">
                  {t("gate.score")}
                </span>
                <span className={`text-[12px] font-semibold ${getScoreTextColor(score)}`}>
                  {scorePct}%
                </span>
              </div>
              <div className="h-1.5 w-full bg-[var(--bg-card)] rounded-full overflow-hidden">
                <div
                  className={`h-full ${getScoreColor(score)} rounded-full transition-all duration-500`}
                  style={{ width: `${scorePct}%` }}
                />
              </div>
            </div>

            {/* Content preview */}
            <div className="mb-3 min-h-[40px]">
              {preview ? (
                <p className="text-[12px] text-[var(--text-muted)] leading-relaxed whitespace-pre-wrap break-words">
                  {preview}
                  {preview.length >= 100 && (
                    <span className="text-[var(--text-muted)]">...</span>
                  )}
                </p>
              ) : (
                <p className="text-[12px] text-[var(--text-muted)] italic">{t("common.empty")}</p>
              )}
            </div>

            {/* Score explanation */}
            {prioritizedExplanation && (
              <p className="text-[12px] text-[var(--text-muted)] mb-2 leading-relaxed line-clamp-2">
                {prioritizedExplanation}
              </p>
            )}

            {continuityDirections.length > 0 && (
              <div className="mb-3 rounded-lg bg-[rgba(122,150,187,0.10)] border border-[rgba(122,150,187,0.22)] p-2">
                <div className="mb-1 flex items-center justify-between gap-2">
                  <p className="text-[11px] font-medium text-[var(--cinema-azure)]">
                    {t("continuity.diagnosticsTitle")}
                  </p>
                  {directorIntentScore !== null && (
                    <span className="text-[11px] font-medium text-[var(--cinema-azure)]">
                      {t("continuity.directorIntentScoreLabel")} {Math.round(directorIntentScore * 100)}%
                    </span>
                  )}
                </div>
                {continuityDirections.slice(0, 2).map((direction, index) => (
                  <div
                    key={`${direction.sceneBeat}-${direction.transitionIntent}-${index}`}
                    className="text-[11px] text-[var(--text-body)] leading-relaxed"
                  >
                    <div>
                      {t("continuity.sceneBeatLabel")} {direction.sceneBeat || t("continuity.unknown")}
                    </div>
                    {direction.transitionIntent && (
                      <div>
                        {t("continuity.transitionIntentLabel")} {direction.transitionIntent}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Select button */}
            <button
              onClick={() => handleToggle(candidate.id)}
              className={`w-full text-xs font-medium py-1.5 px-3 rounded-lg transition-all cursor-pointer ${
                isSelected
                  ? "bg-[var(--fortune-red)] text-white shadow-sm"
                  : isAtMax
                  ? "bg-[var(--bg-card)] text-[var(--text-muted)] cursor-not-allowed"
                  : "bg-[var(--bg-card)] text-[var(--text-h1)] hover:bg-[rgba(215,92,112,0.18)]"
              }`}
              disabled={!isSelected && isAtMax}
            >
              {isSelected ? t("review.selected") : t("step.select")}
            </button>

            {/* Edit link */}
            <div className="text-center mt-1.5">
              <button
                onClick={() => onEdit(candidate.id)}
                className="text-[12px] text-[var(--text-muted)] hover:text-[var(--fortune-red)] transition-colors cursor-pointer"
              >
                {"✎"} {t("step.edit")}
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
