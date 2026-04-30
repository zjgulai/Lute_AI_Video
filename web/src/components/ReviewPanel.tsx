"use client";

import React, { useState } from "react";
import type { AuditReport, ReviewState } from "./types";
import { Clock, FileText, PenSquare, Image } from "lucide-react";
import AuditScoreCard from "./AuditScoreCard";
import { useI18n } from "@/i18n/I18nProvider";

interface Props {
  reviewState: ReviewState;
  currentReview: string;
  onAction: (action: "approve" | "reject" | "request_changes", notes?: string) => void;
  loading: boolean;
}

const REVIEW_ICON_MAP: Record<string, React.ComponentType<{ size?: number; strokeWidth?: number; className?: string }>> = {
  strategy_review: Clock,
  script_review: FileText,
  edit_review: PenSquare,
  thumbnail_review: Image,
};

const REVIEW_CONFIG: Record<string, { titleKey: string; subtitleKey: string; descKey: string; iconKey: string }> = {
  strategy_review: {
    titleKey: "review.strategy.title",
    subtitleKey: "review.strategy.subtitle",
    descKey: "review.strategy.desc",
    iconKey: "strategy_review",
  },
  script_review: {
    titleKey: "review.script.title",
    subtitleKey: "review.script.subtitle",
    descKey: "review.script.desc",
    iconKey: "script_review",
  },
  edit_review: {
    titleKey: "review.edit.title",
    subtitleKey: "review.edit.subtitle",
    descKey: "review.edit.desc",
    iconKey: "edit_review",
  },
  thumbnail_review: {
    titleKey: "review.thumbnail.title",
    subtitleKey: "review.thumbnail.subtitle",
    descKey: "review.thumbnail.desc",
    iconKey: "thumbnail_review",
  },
};

const AUDIT_CHECKPOINT: Record<string, string> = {
  strategy_review: "strategy",
  script_review: "script",
  edit_review: "edit",
  thumbnail_review: "thumbnail",
};

const getTypeLabel = (key: string, t: (k: string) => string) => {
  const map: Record<string, string> = {
    tutorial: "reviewType.tutorial",
    customer_testimonial: "reviewType.customer_testimonial",
    product_usage: "reviewType.product_usage",
    industry_insight: "reviewType.industry_insight",
    unboxing: "reviewType.unboxing",
    pain_point: "reviewType.pain_point",
    product_demo: "reviewType.product_demo",
  };
  return t(map[key] || "") || key;
};

export default function ReviewPanel({ reviewState, currentReview, onAction, loading }: Props) {
  const { t } = useI18n();
  const [notes, setNotes] = useState("");
  const [expandedBriefs, setExpandedBriefs] = useState<Set<string>>(new Set());
  const [expandedScripts, setExpandedScripts] = useState<Set<string>>(new Set());
  const [selectedThumbnails, setSelectedThumbnails] = useState<Record<string, string>>({});

  const config = REVIEW_CONFIG[currentReview];
  const s = reviewState.state;
  const checkpointKey = AUDIT_CHECKPOINT[currentReview];
  const auditReport: AuditReport | null = checkpointKey ? s?.audit_reports?.[checkpointKey] || null : null;

  const toggleBrief = (id: string) => {
    setExpandedBriefs((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const toggleScript = (id: string) => {
    setExpandedScripts((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const renderContent = () => {
    // ── Strategy review: show briefs ──
    if (currentReview === "strategy_review" && s?.weekly_calendar?.briefs) {
      return (
        <div className="space-y-2">
          <p className="text-[11px] text-[#59585E] mb-3">
            {s.weekly_calendar.briefs.length}{t("review.briefs")}
          </p>
          {s.weekly_calendar.briefs.map((brief: any) => {
            const exp = expandedBriefs.has(brief.id);
            return (
              <div key={brief.id} className="apple-card overflow-hidden">
                <button
                  onClick={() => toggleBrief(brief.id)}
                  className="w-full flex items-center gap-2 p-3 cursor-pointer text-left"
                >
                  <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-[#6A2B3A]/10 text-[#6A2B3A] shrink-0">
                    {getTypeLabel(brief.video_type, t) || brief.video_type}
                  </span>
                  <span className="text-[13px] font-medium text-[#35353B] truncate">
                    {brief.topic}
                  </span>
                  <svg
                    width="10" height="10" viewBox="0 0 10 10" fill="none"
                    className={`ml-auto shrink-0 transition-transform ${exp ? "rotate-180" : ""}`}
                  >
                    <path d="M2.5 3.5L5 6.5L7.5 3.5" stroke="#9FA0A0" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </button>
                {exp && (
                  <div className="px-3 pb-3 space-y-2 animate-slide-down">
                    <p className="text-xs text-[#59585E]">{brief.key_message}</p>
                    {brief.usp_priority?.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {brief.usp_priority.map((usp: string, i: number) => (
                          <span key={i} className="text-[11px] px-2 py-0.5 rounded-full bg-[#FCE4E2] text-[#59585E] border border-[#EDD3D1]">
                            {usp}
                          </span>
                        ))}
                      </div>
                    )}
                    {brief.target_audience && (
                      <p className="text-[11px] text-[#9FA0A0]">{t("review.targetAudience")}: {brief.target_audience}</p>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      );
    }

    // ── Script review: show scripts ──
    if (currentReview === "script_review" && s?.scripts) {
      return (
        <div className="space-y-2">
          <p className="text-[11px] text-[#59585E] mb-3">{t("review.scripts")} {s.scripts.length}{t("review.scriptsCount")}</p>
          {s.scripts.map((script: any, i: number) => {
            const key = `${script.id}-${script.platform}-${i}`;
            const exp = expandedScripts.has(key);
            return (
              <div key={key} className="apple-card overflow-hidden">
                <button
                  onClick={() => toggleScript(key)}
                  className="w-full flex items-center gap-2 p-3 cursor-pointer text-left"
                >
                  <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-[#59585E]/10 text-[#59585E] shrink-0">
                    {t("platform." + script.platform) || script.platform}
                  </span>
                  <span className="text-[11px] text-[#9FA0A0] font-mono">{script.id}</span>
                  <span className="text-[11px] text-[#9FA0A0]">{script.total_duration}s</span>
                  <svg
                    width="10" height="10" viewBox="0 0 10 10" fill="none"
                    className={`ml-auto shrink-0 transition-transform ${exp ? "rotate-180" : ""}`}
                  >
                    <path d="M2.5 3.5L5 6.5L7.5 3.5" stroke="#9FA0A0" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </button>
                {exp && script.segments?.map((seg: any, i: number) => (
                  <div key={i} className="px-3 pb-2 last:pb-3">
                    <div className="pl-3 border-l-2 border-[#EDD3D1]">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-[11px] font-semibold text-[#59585E]">
                          {t("segment." + seg.segment_type) || seg.segment_type}
                        </span>
                        <span className="text-[11px] text-[#9FA0A0] font-mono">
                          {seg.start_time}s — {seg.end_time}s
                        </span>
                      </div>
                      <p className="text-[13px] text-[#35353B] leading-relaxed">{seg.voiceover}</p>
                      {seg.visual_description && (
                        <div className="flex items-start gap-1.5 mt-1 text-[11px] text-[#9FA0A0]">
                          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" className="mt-0.5 shrink-0">
                            <rect x="1" y="2" width="10" height="8" rx="1" stroke="#9FA0A0" strokeWidth="0.8" />
                            <circle cx="4.5" cy="5.5" r="1.5" stroke="#9FA0A0" strokeWidth="0.8" />
                            <path d="M1 8l2.5-2 2 1.5L8 5l3 3" stroke="#9FA0A0" strokeWidth="0.8" />
                          </svg>
                          {seg.visual_description}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      );
    }

    // ── Thumbnail review: show thumbnail variants ──
    if (currentReview === "thumbnail_review" && s?.thumbnail_sets) {
      return (
        <div className="space-y-3">
          {s.thumbnail_sets.map((ts: any, idx: number) => (
            <div key={`ts-${idx}`} className="apple-card p-3 space-y-2">
              <p className="text-[11px] font-semibold text-[#59585E]">{ts.script_id}</p>
              <div className="grid grid-cols-2 gap-2">
                {(ts.variants || []).map((v: any) => {
                  const selected = selectedThumbnails[ts.script_id] === v.variant_id;
                  return (
                    <button
                      key={v.variant_id}
                      onClick={() => setSelectedThumbnails((prev) => ({ ...prev, [ts.script_id]: v.variant_id }))}
                      className={`apple-card p-3 text-left cursor-pointer transition-all ${
                        selected ? "ring-2 ring-[#6A2B3A] ring-offset-2" : "hover:shadow-md"
                      }`}
                    >
                      <div className="bg-gradient-to-br from-[#FCE4E2] to-[#EDD3D1] rounded-lg h-20 flex items-center justify-center mb-2">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="#9FA0A0">
                          <rect x="3" y="3" width="18" height="18" rx="3" />
                          <circle cx="9" cy="9" r="3" />
                          <path d="M3 15l4.5-4 3.5 3 4.5-4.5L21 15" />
                        </svg>
                      </div>
                      <div className="text-xs font-semibold text-[#35353B]">{t("review.variant")} {v.variant_id}</div>
                      <div className="text-[11px] text-[#59585E] line-clamp-2">{v.concept}</div>
                      {selected && (
                        <div className="text-[11px] font-semibold text-[#6A2B3A] mt-1 flex items-center gap-1">
                          <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                            <path d="M2 5.5L4 7.5L8 2.5" stroke="#6A2B3A" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                          </svg>
                          {t("review.selected")}
                        </div>
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      );
    }

    // ── Fallback: raw data ──
    return (
      <details className="text-xs text-[#9FA0A0] cursor-pointer">
        <summary>{t("review.viewRaw")}</summary>
        <pre className="mt-2 p-3 rounded-lg bg-[#FCE4E2] overflow-auto text-[11px] max-h-60 border border-[#EDD3D1]">
          {JSON.stringify(s, null, 2)}
        </pre>
      </details>
    );
  };

  if (!config) return null;

  return (
    <div className="space-y-3 animate-slide-up">
      {/* Review card */}
      <div className="apple-card overflow-hidden">
        <div className="p-3 space-y-2">
          {/* Header */}
          <div className="flex items-center gap-3">
            <span className="w-9 h-9 rounded-xl bg-[#6A2B3A]/5 text-[#6A2B3A] flex items-center justify-center shrink-0">
              {React.createElement(REVIEW_ICON_MAP[config.iconKey] || Clock, { size: 20, strokeWidth: 1.5 })}
            </span>
            <div>
              <h2 className="text-base font-semibold text-[#35353B]">{t(config.titleKey)}</h2>
              <p className="text-xs text-[#59585E] mt-0.5">{t(config.subtitleKey)}</p>
            </div>
          </div>
          <p className="text-xs text-[#9FA0A0] leading-relaxed">{t(config.descKey)}</p>

          {/* Audit Score */}
          {auditReport ? (
            <AuditScoreCard report={auditReport} />
          ) : (
            <div className="text-center py-4 rounded-xl bg-[#FCE4E2] border border-[#EDD3D1]">
              <p className="text-xs text-[#9FA0A0]">{t("review.noAudit")}</p>
            </div>
          )}

          {/* Review content */}
          <div>{renderContent()}</div>

          {/* Decision */}
          <div className="border-t border-[#EDD3D1] pt-3 space-y-2">
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder={t("review.notes")}
              className="apple-input resize-none"
              rows={2}
            />
            <div className="flex items-center gap-2">
              {/* Primary action: Approve — full green fill, largest */}
              <button onClick={() => onAction("approve", notes)} disabled={loading}
                className="flex-1 flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-xl text-sm font-semibold text-white bg-[#6A2B3A] hover:bg-[#4E1F2A] active:scale-[0.98] transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer shadow-sm">
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path d="M2.5 7.5L5.5 10.5L11.5 3.5" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                {t("review.approve")}
              </button>
              {/* Secondary action: Request Changes — outline */}
              <button onClick={() => onAction("request_changes", notes)} disabled={loading}
                className="px-3.5 py-2.5 rounded-xl text-xs font-medium text-[#59585E] bg-white border border-[#EDD3D1] hover:border-[#D9A8A3] hover:text-[#35353B] active:scale-[0.98] transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer">
                {t("review.requestChanges")}
              </button>
              {/* Destructive action: Reject — subtle red, rightmost */}
              <button onClick={() => onAction("reject", notes)} disabled={loading}
                className="px-3 py-2.5 rounded-xl text-xs font-medium text-[#C45B50] bg-white border border-[#ffe0dd] hover:bg-[#fff5f5] hover:border-[#C45B50]/30 active:scale-[0.98] transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer">
                {t("review.reject")}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
