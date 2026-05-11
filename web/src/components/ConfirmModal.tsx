"use client";

import { X } from "@phosphor-icons/react";
import { type ReactNode } from "react";

interface Props {
  open: boolean;
  title: ReactNode;
  body?: ReactNode;
  confirmLabel: ReactNode;
  confirmVariant?: "danger" | "primary";
  cancelLabel: ReactNode;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmModal({
  open,
  title,
  body,
  confirmLabel,
  confirmVariant = "danger",
  cancelLabel,
  onConfirm,
  onCancel,
}: Props) {
  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-title"
      className="fixed inset-0 z-[100] flex items-center justify-center px-4"
      style={{ background: "rgba(0,0,0,0.4)" }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onCancel();
      }}
    >
      <div className="apple-card w-full max-w-sm p-6 flex flex-col gap-4 animate-in fade-in zoom-in-95 duration-200">
        <div className="flex items-start justify-between gap-3">
          <h2 id="confirm-title" className="text-[15px] font-semibold text-[var(--text-h1)] flex-1">
            {title}
          </h2>
          <button
            onClick={onCancel}
            aria-label="Close"
            className="w-6 h-6 rounded-md flex items-center justify-center hover:bg-[var(--bg-panel)] transition-colors"
          >
            <X size={16} weight="bold" className="text-[var(--text-muted)]" />
          </button>
        </div>

        {body && <p className="text-[13px] text-[var(--text-body)] leading-relaxed">{body}</p>}

        <div className="flex gap-2 pt-2">
          <button
            onClick={onCancel}
            className="flex-1 px-4 py-2 rounded-lg text-[13px] font-medium border border-[var(--border-default)] text-[var(--text-body)] hover:bg-[var(--bg-panel)] active:scale-[0.98] transition-all"
          >
            {cancelLabel}
          </button>
          <button
            onClick={onConfirm}
            className={`flex-1 px-4 py-2 rounded-lg text-[13px] font-medium text-white active:scale-[0.98] transition-all ${
              confirmVariant === "danger"
                ? "bg-[var(--neon-red)] hover:opacity-90"
                : "bg-[var(--fortune-red)] hover:opacity-90"
            }`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
