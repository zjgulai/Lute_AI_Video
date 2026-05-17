"use client";

import React, { useEffect, useState } from "react";
import { useI18n } from "@/i18n/I18nProvider";
import { X, CheckCircle } from "@phosphor-icons/react";

interface Props {
  result: Record<string, unknown>;
  onDismiss?: () => void;
}

export default function CreativeSummary({ result, onDismiss }: Props) {
  const { t } = useI18n();
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    const timer = setTimeout(() => {
      setVisible(false);
      onDismiss?.();
    }, 3000);
    return () => clearTimeout(timer);
  }, [onDismiss]);

  if (!visible || !result) return null;

  const scripts = (result.scripts as Record<string, unknown>[]) || [];
  const briefs = (result.briefs as Record<string, unknown>[]) || [];
  const audit = (result.audit_report as Record<string, unknown>) || {};
  const productName = (scripts[0]?.product_name as string) || (briefs[0]?.topic as string) || "";
  const duration = (result.video_duration as number) || 0;
  const score = (audit.overall_score as number) || 0;
  const platforms = briefs.map((b) => b.platform as string | undefined).filter(Boolean) || [];

  return (
    <div className="fixed bottom-6 right-6 z-50 animate-slide-up">
      <div className="apple-card p-4 min-w-[240px] shadow-lg border border-[var(--color-accent)]/10">
        <div className="flex items-start justify-between mb-2">
          <div className="flex items-center gap-2">
            <CheckCircle size={16} weight="fill" className="text-[var(--jade-accent)]" />
            <span className="text-sm font-semibold text-[var(--color-text-primary)]">
              {t("creativeSummary.title")}
            </span>
          </div>
          <button
            onClick={() => { setVisible(false); onDismiss?.(); }}
            className="text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)] transition-colors"
          >
            <X size={14} weight="fill" />
          </button>
        </div>

        <div className="space-y-1.5">
          {productName && (
            <div className="flex justify-between text-xs">
              <span className="text-[var(--color-text-tertiary)]">{t("creativeSummary.product")}</span>
              <span className="text-[var(--color-text-primary)] font-medium truncate max-w-[120px]">{productName}</span>
            </div>
          )}
          {duration > 0 && (
            <div className="flex justify-between text-xs">
              <span className="text-[var(--color-text-tertiary)]">{t("creativeSummary.duration")}</span>
              <span className="text-[var(--color-text-primary)] font-medium">{duration}s</span>
            </div>
          )}
          {score > 0 && (
            <div className="flex justify-between text-xs">
              <span className="text-[var(--color-text-tertiary)]">{t("creativeSummary.quality")}</span>
              <span className="text-[var(--jade-accent)] font-medium">{Math.round(score * 100)}%</span>
            </div>
          )}
          {platforms.length > 0 && (
            <div className="flex justify-between text-xs">
              <span className="text-[var(--color-text-tertiary)]">{t("creativeSummary.platforms")}</span>
              <span className="text-[var(--color-text-primary)] font-medium">{platforms.length}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
