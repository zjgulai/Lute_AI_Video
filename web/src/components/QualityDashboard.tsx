"use client";

import { useI18n } from "@/i18n/I18nProvider";
import { AuditReport } from "./types";
import { WarningCircle } from "@phosphor-icons/react";

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
        bg: "bg-[rgba(120,175,140,0.10)]",
        text: "text-[var(--jade-accent)]",
        border: "border-[rgba(120,175,140,0.20)]",
        bar: "bg-[var(--jade-accent)]",
        dot: "bg-[var(--jade-accent)]",
        ring: "ring-[rgba(120,175,140,0.20)]",
      };
    case "WARN":
      return {
        bg: "bg-[rgba(220,190,120,0.10)]",
        text: "text-[var(--gold-foil)]",
        border: "border-[rgba(220,190,120,0.20)]",
        bar: "bg-[var(--gold-foil)]",
        dot: "bg-[var(--gold-foil)]",
        ring: "ring-[rgba(220,190,120,0.20)]",
      };
    case "FAIL":
      return {
        bg: "bg-[rgba(140,60,75,0.10)]",
        text: "text-[var(--crimson-mist)]",
        border: "border-[rgba(140,60,75,0.20)]",
        bar: "bg-[var(--crimson-mist)]",
        dot: "bg-[var(--crimson-mist)]",
        ring: "ring-[rgba(140,60,75,0.20)]",
      };
    default:
      return {
        bg: "bg-[rgba(215,92,112,0.09)]",
        text: "text-[var(--text-muted)]",
        border: "border-[rgba(215,92,112,0.18)]",
        bar: "bg-[rgba(215,92,112,0.18)]",
        dot: "bg-[var(--text-muted)]",
        ring: "ring-[rgba(215,92,112,0.18)]",
      };
  }
}

function ScoreBar({ score, color }: { score: number; color: string }) {
  const pct = Math.round(Math.min(score, 1) * 100);
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 bg-[var(--bg-card)] rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ease-out ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-[11px] font-semibold text-[var(--text-h1)] tabular-nums w-8 text-right">
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
        <div className="w-14 h-14 rounded-2xl bg-[var(--bg-card)] flex items-center justify-center mx-auto mb-3">
          <WarningCircle size={28} weight="fill" className="text-[var(--text-muted)]" />
        </div>
        <p className="text-sm font-medium text-[var(--text-muted)] mb-1">{t("quality.noData")}</p>
        <p className="text-xs text-[var(--text-muted)]">
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
            <p className="text-[11px] font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-1">
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
            <p className="text-[11px] font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-1">
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
          <p className="text-xs text-[var(--text-muted)] mt-2 leading-relaxed">
            {qualityReport.summary}
          </p>
        )}
      </div>

      {/* Criteria list */}
      {criteria.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-[11px] font-semibold text-[var(--text-muted)] uppercase tracking-wider px-1">
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
                    <span className="text-xs font-semibold text-[var(--text-h1)] truncate">
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
                  <p className="text-[11px] text-[var(--text-muted)] mt-1.5 leading-relaxed">
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
