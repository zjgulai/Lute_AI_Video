"use client";

import React from "react";
import { useI18n } from "@/i18n/I18nProvider";

interface Props {
  label?: string;
  progress?: number;
  onCancel?: () => void;
}

export default function ExecutionBar({ label, progress, onCancel }: Props) {
  const { t } = useI18n();

  if (!label && !progress) return null;

  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 animate-slide-up">
      <div className="flex items-center gap-3 bg-[var(--color-text-primary)] text-white px-5 py-3 rounded-full shadow-lg">
        {/* Spinner */}
        <div className="relative w-4 h-4">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" className="animate-spin">
            <circle cx="12" cy="12" r="10" stroke="rgba(255,255,255,0.2)" strokeWidth="3" />
            <path d="M12 2a10 10 0 0 1 10 10" stroke="white" strokeWidth="3" strokeLinecap="round" />
          </svg>
        </div>

        {/* Label */}
        <span className="text-sm font-medium">{label || t("execution.generating")}</span>

        {/* Progress */}
        {progress !== undefined && progress > 0 && (
          <span className="text-xs text-white/70 font-mono">{progress}%</span>
        )}

        {/* Cancel */}
        {onCancel && (
          <button
            onClick={onCancel}
            className="text-xs text-white/60 hover:text-white ml-1 transition-colors"
          >
            {t("execution.cancel")}
          </button>
        )}
      </div>
    </div>
  );
}
