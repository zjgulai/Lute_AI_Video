"use client";

import React from "react";
import { useI18n } from "@/i18n/I18nProvider";

interface Props {
  values: Record<string, string>;
  cardLabels: Record<string, string>;
}

export default function LiveSummary({ values, cardLabels }: Props) {
  const { t } = useI18n();

  const filledCount = Object.values(values).filter((v) => v && v.trim().length > 0).length;
  const totalCount = Object.keys(cardLabels).length;
  const progress = totalCount > 0 ? Math.round((filledCount / totalCount) * 100) : 0;

  const entries = Object.entries(values)
    .filter(([, v]) => v && v.trim().length > 0)
    .map(([k, v]) => ({
      label: cardLabels[k] || k,
      value: v.length > 30 ? v.slice(0, 30) + "..." : v,
    }));

  return (
    <div className="apple-card p-4 sticky top-4">
      <h3 className="text-sm font-semibold text-[var(--color-text-primary)] mb-3">
        {t("summary.title")}
      </h3>

      {/* 进度条 */}
      <div className="mb-4">
        <div className="flex justify-between text-xs text-[var(--color-text-tertiary)] mb-1.5">
          <span>{t("summary.progress")}</span>
          <span>{progress}%</span>
        </div>
        <div className="h-1.5 bg-[var(--color-border-light)] rounded-full overflow-hidden">
          <div
            className="h-full bg-[var(--color-accent)] rounded-full transition-all duration-500"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {/* 摘要条目 */}
      {entries.length === 0 ? (
        <p className="text-xs text-[var(--color-text-tertiary)] leading-relaxed">
          {t("summary.empty")}
        </p>
      ) : (
        <div className="space-y-2">
          {entries.map((entry) => (
            <div key={entry.label} className="flex gap-2">
              <span className="text-[12px] text-[var(--color-text-tertiary)] shrink-0 min-w-[3rem]">
                {entry.label}
              </span>
              <span className="text-xs text-[var(--color-text-primary)] truncate">
                {entry.value}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* 完成提示 */}
      {progress === 100 && (
        <div className="mt-3 pt-3 border-t border-[var(--color-border-light)]">
          <p className="text-xs text-[var(--jade-accent)] font-medium">{t("summary.complete")}</p>
        </div>
      )}
    </div>
  );
}
