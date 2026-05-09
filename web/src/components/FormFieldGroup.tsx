"use client";

import { type ReactNode } from "react";

interface Props {
  fieldId: string;
  label: ReactNode;
  required?: boolean;
  hint?: ReactNode;
  error?: ReactNode;
  className?: string;
  children: ReactNode;
}

export default function FormFieldGroup({
  fieldId,
  label,
  required,
  hint,
  error,
  className = "",
  children,
}: Props) {
  const hintId = hint ? `${fieldId}-hint` : undefined;
  const errorId = error ? `${fieldId}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;

  return (
    <div className={`space-y-1 ${className}`} data-field-group={fieldId}>
      <label
        htmlFor={fieldId}
        className="block text-[12px] font-medium text-[var(--text-body)]"
      >
        {label}
        {required && (
          <span
            aria-label="required"
            className="ml-1 text-[var(--fortune-red)] font-semibold"
          >
            *
          </span>
        )}
      </label>

      <FieldChild
        fieldId={fieldId}
        required={required}
        describedBy={describedBy}
        hasError={!!error}
      >
        {children}
      </FieldChild>

      {hint && !error && (
        <p id={hintId} className="text-[11px] text-[var(--text-muted)] leading-snug">
          {hint}
        </p>
      )}

      {error && (
        <p
          id={errorId}
          role="alert"
          className="text-[11px] text-[var(--crimson-mist)] leading-snug font-medium"
        >
          {error}
        </p>
      )}
    </div>
  );
}

interface FieldChildProps {
  fieldId: string;
  required?: boolean;
  describedBy?: string;
  hasError: boolean;
  children: ReactNode;
}

function FieldChild({ fieldId, required, describedBy, hasError, children }: FieldChildProps) {
  const child = children as React.ReactElement<Record<string, unknown>>;
  if (!child || typeof child !== "object" || !("props" in child)) {
    return <>{children}</>;
  }

  const existingDescribedBy = (child.props["aria-describedby"] as string | undefined) || "";
  const mergedDescribedBy = [existingDescribedBy, describedBy].filter(Boolean).join(" ") || undefined;

  return (
    <child.type
      {...child.props}
      id={(child.props.id as string | undefined) || fieldId}
      name={(child.props.name as string | undefined) || fieldId}
      aria-required={required ? "true" : undefined}
      aria-invalid={hasError ? "true" : undefined}
      aria-describedby={mergedDescribedBy}
    />
  );
}
