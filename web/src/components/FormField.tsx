"use client";

import { type ReactNode } from "react";
import { WarningCircle } from "@phosphor-icons/react";

interface Props {
  id: string;
  label?: ReactNode;
  hint?: ReactNode;
  required?: boolean;
  error?: string | null;
  children: (a11y: {
    id: string;
    "aria-invalid": boolean;
    "aria-describedby": string | undefined;
    "aria-required": boolean | undefined;
  }) => ReactNode;
}

export function FormField({ id, label, hint, required, error, children }: Props) {
  const hintId = hint ? `${id}-hint` : undefined;
  const errId = error ? `${id}-err` : undefined;
  const describedBy = [hintId, errId].filter(Boolean).join(" ") || undefined;

  return (
    <div className="space-y-1.5">
      {label && (
        <label htmlFor={id} className="block text-[12px] font-medium text-[var(--text-body)]">
          {label}
          {required && <span aria-hidden="true" className="ml-0.5 text-[var(--neon-red)]">*</span>}
        </label>
      )}
      {children({
        id,
        "aria-invalid": !!error,
        "aria-describedby": describedBy,
        "aria-required": required ? true : undefined,
      })}
      {hint && !error && (
        <p id={hintId} className="text-[11px] text-[var(--text-muted)]">{hint}</p>
      )}
      {error && (
        <p id={errId} role="alert" className="flex items-start gap-1.5 text-[11px] text-[var(--neon-red)]">
          <WarningCircle size={12} weight="fill" className="shrink-0 mt-0.5" aria-hidden="true" />
          <span>{error}</span>
        </p>
      )}
    </div>
  );
}
