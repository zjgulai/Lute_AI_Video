"use client";

import React from "react";
import { useI18n } from "@/i18n/I18nProvider";
import { Clock, FileText, CheckCircle, Image, Search, Video, PenSquare, Headphones, Type, BarChart3, Repeat } from "lucide-react";

// ── Pipeline stages with human-readable labels ──
const STAGES = [
  {
    key: "strategy",
    label: "pstage.strategy",
    iconKey: "strategy",
    check: (s: any) => s?.weekly_calendar,
    auditCheck: (s: any) => s?.audit_reports?.strategy,
  },
  {
    key: "script",
    label: "pstage.script",
    iconKey: "script",
    check: (s: any) => s?.scripts,
    auditCheck: (s: any) => s?.audit_reports?.script,
  },
  {
    key: "compliance",
    label: "pstage.compliance",
    iconKey: "compliance",
    check: (s: any) => s?.compliance_reports,
  },
  {
    key: "storyboard",
    label: "pstage.storyboard",
    iconKey: "storyboard",
    check: (s: any) => s?.storyboards,
  },
  {
    key: "asset_sourcing",
    label: "pstage.asset_sourcing",
    iconKey: "asset_sourcing",
    check: (s: any) => s?.asset_plans,
  },
  {
    key: "media_gen",
    label: "pstage.media_gen",
    iconKey: "media_gen",
    check: (s: any) => s?.generated_assets,
  },
  {
    key: "editing",
    label: "pstage.editing",
    iconKey: "editing",
    check: (s: any) => s?.edit_compositions,
    auditCheck: (s: any) => s?.audit_reports?.edit,
  },
  {
    key: "audio",
    label: "pstage.audio",
    iconKey: "audio",
    check: (s: any) => s?.audio_plans,
  },
  {
    key: "caption",
    label: "pstage.caption",
    iconKey: "caption",
    check: (s: any) => s?.caption_plans,
  },
  {
    key: "thumbnail",
    label: "pstage.thumbnail",
    iconKey: "thumbnail",
    check: (s: any) => s?.thumbnail_sets,
    auditCheck: (s: any) => s?.audit_reports?.thumbnail,
  },
  {
    key: "distribution",
    label: "pstage.distribution",
    iconKey: "distribution",
    check: (s: any) => s?.distribution_plans,
  },
  {
    key: "analytics",
    label: "pstage.analytics",
    iconKey: "analytics",
    check: (s: any) => s?.analytics_reports,
  },
];

interface Props {
  state: any;
  currentReview: string | null | undefined;
  pipelineComplete: boolean;
  threadId?: string|null|undefined;
  onReset?: () => void;
}

const STAGE_ICON_MAP: Record<string, React.ComponentType<{ size?: number; strokeWidth?: number; className?: string }>> = {
  strategy: Clock,
  script: FileText,
  compliance: CheckCircle,
  storyboard: Image,
  asset_sourcing: Search,
  media_gen: Video,
  editing: PenSquare,
  audio: Headphones,
  caption: Type,
  thumbnail: Image,
  analytics: BarChart3,
  distribution: Repeat,
};

// ── Review node → stage index mapping ──
const REVIEW_TO_STAGE: Record<string, number> = {
  strategy_review: 1,
  script_review: 3,
  edit_review: 8,
  thumbnail_review: 11,
};

export default function PipelineMonitor({ state, currentReview, pipelineComplete, threadId, onReset }: Props) {
  const { t } = useI18n();
  const activeIdx = currentReview ? REVIEW_TO_STAGE[currentReview] ?? 11 : -1;

  return (
    <div className="px-4 py-3 space-y-0">
      {/* Thread context bar */}
      {threadId && (
        <div className="flex items-center justify-between mb-2 pb-2 border-b border-[#EDD3D1]">
          <span className="text-[11px] text-[#9FA0A0] font-mono">#{threadId}</span>
          {onReset && !pipelineComplete && (
            <button onClick={onReset} className="text-[11px] text-[#9FA0A0] hover:text-[#C45B50] transition-colors cursor-pointer">
              {t("pipeline.abandon")}
            </button>
          )}
        </div>
      )}

      <div className="flex items-center justify-between mb-3">
        <h3 className="text-[11px] font-semibold text-[#59585E] uppercase tracking-wider flex items-center gap-1.5">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="shrink-0">
            <circle cx="7" cy="7" r="5.5" stroke="#59585E" strokeWidth="1" />
            <path d="M7 4v3.5l2.5 1.5" stroke="#59585E" strokeWidth="1" strokeLinecap="round" />
          </svg>
          {t("pipeline.progress")}
        </h3>
        <span className="text-[11px] text-[#9FA0A0] font-mono">
          {STAGES.filter((s) => s.check(state)).length}/{STAGES.length}
        </span>
      </div>

      {/* Stage timeline */}
      <div className="relative">
        {/* Vertical line */}
        <div className="absolute left-[15px] top-2 bottom-2 w-px bg-[#EDD3D1]" />

        <div className="space-y-0">
          {STAGES.map((stage, i) => {
            const done = stage.check(state);
            const hasAudit = stage.auditCheck && stage.auditCheck(state);
            const isActive = i === activeIdx;
            const isPast = i < activeIdx;

            let dotColor = "bg-[#EDD3D1]";
            let dotRing = "";
            if (done || hasAudit || isPast) {
              dotColor = "bg-[#6A2B3A]";
              dotRing = "ring-2 ring-[#6A2B3A]/20";
            }
            if (isActive) {
              dotColor = "bg-[#6A2B3A]";
              dotRing = "ring-4 ring-[#6A2B3A]/30 animate-pulse";
            }

            return (
              <div
                key={stage.key}
              className={`relative flex items-center gap-3 pl-8 py-1.5 rounded-lg transition-all ${
                isActive ? "bg-[#6A2B3A]/5 -mx-1 px-1" : ""
              }`}
              >
                {/* Dot */}
                <div
                  className={`absolute left-[9px] w-3 h-3 rounded-full ${dotColor} ${dotRing} transition-all duration-300`}
                />

                {/* Icon */}
                {React.createElement(STAGE_ICON_MAP[stage.iconKey] || Clock, { size: 16, strokeWidth: 1.5, className: "w-4 h-4 shrink-0 text-[#59585E]" })}

                {/* Label + Status */}
                <div className="flex-1 min-w-0">
                  <span
                    className={`text-[13px] font-medium transition-colors ${
                      isActive
                        ? "text-[#6A2B3A]"
                        : done || isPast || pipelineComplete
                        ? "text-[#35353B]"
                        : "text-[#9FA0A0]"
                    }`}
                  >
                    {t(stage.label)}
                  </span>
                  {hasAudit && (
                    <span className="ml-2 text-[11px] text-[#ff9f0a] font-semibold bg-[#ff9f0a]/10 px-1.5 py-0.5 rounded-full">
                      {t("pipeline.selfAudited")}
                    </span>
                  )}
                </div>

                {/* Checkmark */}
                {(done || hasAudit) && (
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="shrink-0">
                    <path
                      d="M3 7.5L5.5 10L11 4"
                      stroke="#6A2B3A"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Pipeline complete badge */}
      {pipelineComplete && (
        <div className="pt-2">
          <div className="flex items-center justify-center gap-2 py-2 rounded-lg bg-[#6A2B3A]/10 text-[#6A2B3A] text-xs font-semibold">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path
                d="M3 7.5L5.5 10L11 4"
                stroke="#6A2B3A"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            {t("pipeline.allDone")}
          </div>
        </div>
      )}
    </div>
  );
}
