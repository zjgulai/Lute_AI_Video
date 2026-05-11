"use client";

import React from "react";
import { useI18n } from "@/i18n/I18nProvider";
import { tCardCopy } from "@/i18n/cardCopyEn";

type ConnectorTier = "primary" | "gold" | "glow" | "complete" | "dashed";

interface Props {
  text?: string;
  tier?: ConnectorTier;
}

const TIER_LINE_CLASS: Record<ConnectorTier, string> = {
  primary: "connector-primary",
  gold: "connector-gold",
  glow: "connector-glow",
  complete: "connector-complete",
  dashed: "connector-dashed",
};

const TIER_TEXT_CLASS: Record<ConnectorTier, string> = {
  primary: "text-[var(--text-muted)]",
  gold: "text-[var(--gold-foil)]",
  glow: "text-[var(--neon-red)]",
  complete: "text-[var(--jade-accent)]",
  dashed: "text-[var(--text-placeholder)]",
};

const TIER_ARROW_BORDER: Record<ConnectorTier, string> = {
  primary: "border-t-[var(--line-primary)]",
  gold: "border-t-[var(--line-gold)]",
  glow: "border-t-[var(--line-glow)]",
  complete: "border-t-[var(--line-complete)]",
  dashed: "border-t-[var(--line-dashed)]",
};

export default function CardConnector({ text, tier = "primary" }: Props) {
  const { locale } = useI18n();
  if (!text) return null;
  const displayText = tCardCopy(text, locale) ?? text;

  const lineClass = TIER_LINE_CLASS[tier];
  const textClass = TIER_TEXT_CLASS[tier];
  const arrowClass = TIER_ARROW_BORDER[tier];

  return (
    <div className="flex flex-col items-center py-1 px-4">
      <div className={`w-px h-3 ${lineClass}`} />
      <div className="flex items-center gap-2 my-0.5">
        <div className={`w-8 h-px ${lineClass} opacity-70`} />
        <span className={`text-[12px] italic whitespace-nowrap ${textClass}`}>
          {displayText}
        </span>
        <div className={`w-8 h-px ${lineClass} opacity-70`} />
      </div>
      <div className="relative">
        <div className={`w-px h-3 ${lineClass}`} />
        <div
          className={`absolute -bottom-0.5 left-1/2 -translate-x-1/2 w-0 h-0 border-l-[3px] border-r-[3px] border-t-[3px] border-l-transparent border-r-transparent ${arrowClass}`}
        />
      </div>
    </div>
  );
}
