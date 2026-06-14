"use client";

import React from "react";

interface InlineTooltipProps {
  label: string;
  tooltip: string;
  className?: string;
  placement?: "top" | "bottom";
  tooltipClassName?: string;
}

export default function InlineTooltip({
  label,
  tooltip,
  className = "",
  placement = "bottom",
  tooltipClassName = "",
}: InlineTooltipProps) {
  const placementClassName =
    placement === "top"
      ? "bottom-full left-1/2 mb-2 -translate-x-1/2"
      : "left-1/2 top-full mt-2 -translate-x-1/2";

  return (
    <span className={`relative inline-block group ${className}`.trim()}>
      <span
        tabIndex={0}
        aria-label={tooltip}
        className="inline-block cursor-help decoration-dotted underline-offset-2 focus:outline-none focus:ring-2 focus:ring-[rgba(122,150,187,0.35)] focus:rounded-sm"
      >
        {label}
      </span>
      <span
        role="tooltip"
        className={`pointer-events-none absolute z-10 hidden max-w-[calc(100vw-2rem)] rounded-lg border border-[rgba(122,150,187,0.22)] bg-[var(--bg-card)] p-2 text-[11px] leading-relaxed text-[var(--text-body)] shadow-lg group-hover:block group-focus-within:block group-active:block ${placementClassName} ${tooltipClassName}`.trim()}
      >
        {tooltip}
      </span>
    </span>
  );
}
