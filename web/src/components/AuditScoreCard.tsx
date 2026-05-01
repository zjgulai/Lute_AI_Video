"use client";

import type { AuditReport, AuditCriterion } from "./types";
import { useI18n } from "@/i18n/I18nProvider";

interface Props {
  report: AuditReport;
}

export default function AuditScoreCard({ report }: Props) {
  const { t } = useI18n();
  const score = report.overall_score;
  const status = report.overall_status;

  return (
    <div className="p-3 rounded-xl bg-[var(--bg-card)] border border-[rgba(215,92,112,0.18)] space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-[11px] font-semibold text-[var(--text-muted)] uppercase tracking-wider flex items-center gap-1.5">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
          </svg>
          {t("audit.title")}
        </h3>
        <ScoreBadge score={score} status={status} t={t} />
      </div>

      {/* Score circle + summary */}
      <div className="flex items-center gap-3">
        <div className="relative shrink-0">
          <svg width="56" height="56" viewBox="0 0 56 56">
            <circle cx="28" cy="28" r="24" fill="none" stroke="rgba(215,92,112,0.18)" strokeWidth="5" />
            <circle
              cx="28" cy="28" r="24"
              fill="none"
              stroke={score >= 0.9 ? "#78AF8C" : score >= 0.6 ? "#DCBE78" : "#8C3C4B"}
              strokeWidth="5"
              strokeDasharray={`${score * 151} 151`}
              strokeLinecap="round"
              transform="rotate(-90 28 28)"
            />
          </svg>
          <span className={`absolute inset-0 flex items-center justify-center text-base font-bold ${
            score >= 0.9 ? "text-[var(--jade-accent)]" : score >= 0.6 ? "text-[var(--gold-foil)]" : "text-[var(--crimson-mist)]"
          }`}>
            {Math.round(score * 100)}
          </span>
        </div>
        <div className="min-w-0">
          <p className={`text-sm font-semibold ${
            score >= 0.9 ? "text-[var(--jade-accent)]" : score >= 0.6 ? "text-[var(--gold-foil)]" : "text-[var(--crimson-mist)]"
          }`}>
            {score >= 0.9 ? t("audit.excellent")
              : score >= 0.6 ? t("audit.pendingReview")
              : t("audit.rejected")}
          </p>
          <p className="text-[11px] text-[var(--text-muted)] mt-0.5 line-clamp-2">{report.summary}</p>
        </div>
      </div>

      {/* Criteria bars */}
      <div className="space-y-2">
        {report.criteria.map((c: AuditCriterion) => (
          <div key={c.name}>
            <div className="flex justify-between items-center mb-0.5">
              <span className="text-[11px] text-[var(--text-muted)] truncate mr-2">{c.name}</span>
              <span className="text-[11px] font-medium text-[var(--text-h1)]">{Math.round(c.score * 100)}</span>
            </div>
            <div className="h-1.5 rounded-full bg-[rgba(215,92,112,0.18)] overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  c.status === "PASS" ? "bg-[var(--jade-accent)]"
                  : c.status === "WARN" ? "bg-[var(--gold-foil)]"
                  : "bg-[var(--crimson-mist)]"
                }`}
                style={{ width: `${c.score * 100}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ScoreBadge({ score, status, t }: { score: number; status: string; t: (k: string) => string }) {
  const colors: Record<string, string> = {
    PASS: "bg-[rgba(120,175,140,0.10)] text-[var(--jade-accent)] border-[rgba(120,175,140,0.20)]",
    WARN: "bg-[rgba(220,190,120,0.10)] text-[var(--gold-foil)] border-[rgba(220,190,120,0.20)]",
    FAIL: "bg-[rgba(140,60,75,0.10)] text-[var(--crimson-mist)] border-[rgba(140,60,75,0.20)]",
  };
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-semibold border ${colors[status] || colors.FAIL}`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full ${
          status === "PASS" ? "bg-[var(--jade-accent)]" : status === "WARN" ? "bg-[var(--gold-foil)]" : "bg-[var(--crimson-mist)]"
        }`}
      />
      {Math.round(score * 100)}{t("audit.scoreSuffix")}
    </span>
  );
}
