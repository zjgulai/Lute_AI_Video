"use client";

import { type ReactNode } from "react";

interface Props {
  primaryLabel: ReactNode;
  onPrimary: () => void;
  disabled?: boolean;
  loading?: boolean;
  missingFields?: string[];
  missingLabel?: string;
  secondary?: ReactNode;
  progressText?: ReactNode;
}

export default function StickyActionBar({
  primaryLabel,
  onPrimary,
  disabled,
  loading,
  missingFields = [],
  missingLabel,
  secondary,
  progressText,
}: Props) {
  const hasMissing = disabled && missingFields.length > 0;

  return (
    <div
      data-sticky-action-bar
      className="sticky bottom-0 left-0 right-0 z-30 mt-6 -mx-4 sm:mx-0 px-4 sm:px-0"
    >
      <div className="apple-card p-3 sm:p-4 border border-[var(--border-default)] shadow-[0_-2px_24px_rgba(215,92,112,0.08)] bg-[var(--bg-card)]/95 backdrop-blur-xl">
        <div className="flex flex-col sm:flex-row sm:items-center gap-3">
          <div className="flex-1 min-w-0">
            {progressText && (
              <p className="text-[12px] text-[var(--text-body)] truncate">{progressText}</p>
            )}
            {hasMissing && (
              <p className="text-[11px] text-[var(--text-muted)] mt-0.5 truncate">
                {missingLabel}
                <span className="ml-1 text-[var(--fortune-red)] font-medium">
                  {missingFields.join(" · ")}
                </span>
              </p>
            )}
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {secondary}
            <button
              type="button"
              onClick={onPrimary}
              disabled={disabled || loading}
              className={`apple-btn apple-btn-primary text-sm py-2.5 px-5 transition-all ${
                !disabled && !loading ? "hover:scale-[1.02] shadow-[0_0_12px_rgba(215,92,112,0.25)]" : ""
              }`}
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" className="animate-spin">
                    <circle cx="12" cy="12" r="10" stroke="rgba(255,255,255,0.3)" strokeWidth="3" />
                    <path d="M12 2a10 10 0 0 1 10 10" stroke="white" strokeWidth="3" strokeLinecap="round" />
                  </svg>
                  <span>{primaryLabel}</span>
                </span>
              ) : (
                primaryLabel
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
