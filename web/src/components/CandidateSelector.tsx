"use client";

import { useMemo } from "react";
import { useI18n } from "@/i18n/I18nProvider";

interface Score {
  overall: number;
  breakdown?: any;
  explanation?: string;
}

export interface Candidate {
  id: string;
  variant: "standard" | "creative" | "conservative";
  data: any;
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
  if (score >= 0.8) return "bg-[#6A2B3A]";
  if (score >= 0.5) return "bg-[#ff9500]";
  return "bg-[#C45B50]";
}

function getScoreBgColor(score: number): string {
  if (score >= 0.8) return "bg-[#6A2B3A]/10";
  if (score >= 0.5) return "bg-[#ff9500]/10";
  return "bg-[#C45B50]/10";
}

function getScoreTextColor(score: number): string {
  if (score >= 0.8) return "text-[#6A2B3A]";
  if (score >= 0.5) return "text-[#ff9500]";
  return "text-[#C45B50]";
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

function getDataPreview(data: any): string {
  if (!data) return "";
  if (typeof data === "string") return data.slice(0, 100);
  const str = JSON.stringify(data, null, 2);
  return str.slice(0, 100);
}

function SkeletonCard() {
  return (
    <div className="flex-1 min-w-[200px] max-w-[260px] animate-pulse">
      <div className="apple-card p-4 space-y-3">
        {/* Variant badge skeleton */}
        <div className="flex justify-end">
          <div className="h-4 w-20 rounded-full bg-[#EDD3D1]" />
        </div>
        {/* Score bar skeleton */}
        <div className="space-y-1">
          <div className="h-2 w-full rounded-full bg-[#EDD3D1]" />
          <div className="h-3 w-12 rounded bg-[#EDD3D1]" />
        </div>
        {/* Content preview skeleton */}
        <div className="space-y-1.5">
          <div className="h-2.5 w-full rounded bg-[#EDD3D1]" />
          <div className="h-2.5 w-3/4 rounded bg-[#EDD3D1]" />
          <div className="h-2.5 w-1/2 rounded bg-[#EDD3D1]" />
        </div>
        {/* Button skeleton */}
        <div className="h-8 w-full rounded-lg bg-[#EDD3D1]" />
        {/* Edit link skeleton */}
        <div className="h-3 w-12 mx-auto rounded bg-[#EDD3D1]" />
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

        let borderClass = "border-[#EDD3D1]";
        if (isSelected) borderClass = "border-[#6A2B3A]";
        else if (candidate.recommended) borderClass = "border-[#6A2B3A]";

        return (
          <div
            key={candidate.id}
            className={`flex-1 min-w-[200px] max-w-[260px] apple-card p-4 border-2 transition-all relative ${
              isSelected ? "ring-2 ring-[#6A2B3A]/20" : ""
            } ${borderClass}`}
          >
            {/* AI Recommended badge */}
            {candidate.recommended && (
              <div className="absolute -top-2.5 left-3">
                <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-[#6A2B3A] text-white shadow-sm">
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
                <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-[#6A2B3A] text-white shadow-sm">
                  <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                    <path d="M2 5.5L4 7.5L8 2.5" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </span>
              </div>
            )}

            {/* Variant badge */}
            <div className="flex justify-end mb-2">
              <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${getScoreBgColor(score)} ${getScoreTextColor(score)}`}>
                {t(getVariantLabelKey(candidate.variant))}
              </span>
            </div>

            {/* Score bar */}
            <div className="mb-2">
              <div className="flex items-center justify-between mb-1">
                <span className="text-[10px] text-[#9FA0A0] font-medium">
                  {t("gate.score")}
                </span>
                <span className={`text-[10px] font-semibold ${getScoreTextColor(score)}`}>
                  {scorePct}%
                </span>
              </div>
              <div className="h-1.5 w-full bg-[#FFF0EF] rounded-full overflow-hidden">
                <div
                  className={`h-full ${getScoreColor(score)} rounded-full transition-all duration-500`}
                  style={{ width: `${scorePct}%` }}
                />
              </div>
            </div>

            {/* Content preview */}
            <div className="mb-3 min-h-[40px]">
              {preview ? (
                <p className="text-[11px] text-[#9FA0A0] leading-relaxed whitespace-pre-wrap break-words">
                  {preview}
                  {preview.length >= 100 && (
                    <span className="text-[#9FA0A0]">...</span>
                  )}
                </p>
              ) : (
                <p className="text-[11px] text-[#9FA0A0] italic">{t("common.empty")}</p>
              )}
            </div>

            {/* Score explanation */}
            {candidate.score?.explanation && (
              <p className="text-[9px] text-[#9FA0A0] mb-2 leading-relaxed line-clamp-2">
                {candidate.score.explanation}
              </p>
            )}

            {/* Select button */}
            <button
              onClick={() => handleToggle(candidate.id)}
              className={`w-full text-xs font-medium py-1.5 px-3 rounded-lg transition-all cursor-pointer ${
                isSelected
                  ? "bg-[#6A2B3A] text-white shadow-sm"
                  : isAtMax
                  ? "bg-[#FFF0EF] text-[#9FA0A0] cursor-not-allowed"
                  : "bg-[#FFF0EF] text-[#35353B] hover:bg-[#EDD3D1]"
              }`}
              disabled={!isSelected && isAtMax}
            >
              {isSelected ? t("review.selected") : t("step.select")}
            </button>

            {/* Edit link */}
            <div className="text-center mt-1.5">
              <button
                onClick={() => onEdit(candidate.id)}
                className="text-[10px] text-[#9FA0A0] hover:text-[#6A2B3A] transition-colors cursor-pointer"
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
