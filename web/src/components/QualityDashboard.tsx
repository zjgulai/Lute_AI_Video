"use client";

import { useI18n } from "@/i18n/I18nProvider";
import { AuditReport } from "./types";
import { AlertCircle } from "lucide-react";

interface Props {
  qualityReport: AuditReport | null;
}

function statusIcon(status: string) {
  switch (status) {
    case "PASS":
      return "✅";
    case "WARN":
      return "⚠️";
    case "FAIL":
      return "❌";
    default:
      return "—";
  }
}

function statusColor(status: string) {
  switch (status) {
    case "PASS":
      return {
        bg: "bg-[#30d158]/10",
        text: "text-[#30d158]",
        border: "border-[#30d158]/20",
        bar: "bg-[#30d158]",
        dot: "bg-[#30d158]",
        ring: "ring-[#30d158]/20",
      };
    case "WARN":
      return {
        bg: "bg-[#ff9f0a]/10",
        text: "text-[#ff9f0a]",
        border: "border-[#ff9f0a]/20",
        bar: "bg-[#ff9f0a]",
        dot: "bg-[#ff9f0a]",
        ring: "ring-[#ff9f0a]/20",
      };
    case "FAIL":
      return {
        bg: "bg-[#ff453a]/10",
        text: "text-[#ff453a]",
        border: "border-[#ff453a]/20",
        bar: "bg-[#ff453a]",
        dot: "bg-[#ff453a]",
        ring: "ring-[#ff453a]/20",
      };
    default:
      return {
        bg: "bg-[#e8e8ed]/50",
        text: "text-[#aeaeb2]",
        border: "border-[#e8e8ed]",
        bar: "bg-[#e8e8ed]",
        dot: "bg-[#aeaeb2]",
        ring: "ring-[#e8e8ed]",
      };
  }
}

function ScoreBar({ score, color }: { score: number; color: string }) {
  const pct = Math.round(Math.min(score, 1) * 100);
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 bg-[#f5f5f7] rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ease-out ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-[11px] font-semibold text-[#1d1d1f] tabular-nums w-8 text-right">
        {pct}%
      </span>
    </div>
  );
}

export default function QualityDashboard({ qualityReport }: Props) {
  const { t } = useI18n();
  // Empty state
  if (!qualityReport) {
    return (
      <div className="text-center py-12">
        <div className="w-14 h-14 rounded-2xl bg-[#f5f5f7] flex items-center justify-center mx-auto mb-3">
          <AlertCircle className="w-7 h-7 text-[#aeaeb2]" />
        </div>
        <p className="text-sm font-medium text-[#86868b] mb-1">{t("quality.noData")}</p>
        <p className="text-xs text-[#aeaeb2]">
          {t("quality.hint")}
        </p>
      </div>
    );
  }

  const overall = statusColor(qualityReport.overall_status);
  const overallScorePct = Math.round(Math.min(qualityReport.overall_score, 1) * 100);
  const criteria = qualityReport.criteria || [];

  return (
    <div className="space-y-3">
      {/* Overview card */}
      <div
        className={`apple-card p-4 border-l-4 ${overall.border}`}
      >
        <div className="flex items-start justify-between gap-3 mb-3">
          <div>
            <p className="text-[11px] font-semibold text-[#86868b] uppercase tracking-wider mb-1">
              {t("quality.overallStatus")}
            </p>
            <span
              className={`inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full ${overall.bg} ${overall.text} ${overall.ring} ring-1`}
            >
              <span className={`w-1.5 h-1.5 rounded-full ${overall.dot}`} />
              {qualityReport.overall_status}
            </span>
          </div>
          <div className="text-right">
            <p className="text-[11px] font-semibold text-[#86868b] uppercase tracking-wider mb-1">
              {t("quality.overallScore")}
            </p>
            <span className={`text-lg font-bold ${overall.text}`}>
              {overallScorePct}%
            </span>
          </div>
        </div>

        {/* Overall score bar */}
        <ScoreBar score={qualityReport.overall_score} color={overall.bar} />

        {/* Summary */}
        {qualityReport.summary && (
          <p className="text-xs text-[#86868b] mt-2 leading-relaxed">
            {qualityReport.summary}
          </p>
        )}
      </div>

      {/* Criteria list */}
      {criteria.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-[11px] font-semibold text-[#86868b] uppercase tracking-wider px-1">
            {t("quality.criteria")}
          </h3>
          {criteria.map((c, i) => {
            const colors = statusColor(c.status);
            return (
              <div
                key={i}
                className={`apple-card p-3 border-l-4 ${colors.border}`}
              >
                <div className="flex items-start justify-between gap-2 mb-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-sm shrink-0">{statusIcon(c.status)}</span>
                    <span className="text-xs font-semibold text-[#1d1d1f] truncate">
                      {c.name}
                    </span>
                  </div>
                  <span
                    className={`inline-flex items-center text-[10px] font-semibold px-2 py-0.5 rounded-full shrink-0 ${colors.bg} ${colors.text}`}
                  >
                    {c.status}
                  </span>
                </div>

                {/* Criterion score bar */}
                <ScoreBar score={c.score} color={colors.bar} />

                {/* Observation / reason */}
                {c.reason && (
                  <p className="text-[11px] text-[#86868b] mt-1.5 leading-relaxed">
                    {c.reason}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
