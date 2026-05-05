"use client";

import React, { useState } from "react";
import { useI18n } from "@/i18n/I18nProvider";
import { TEMPLATE_PRESETS } from "@/demo-data";
import { CaretDown, Sparkle } from "@phosphor-icons/react";

interface Props {
  onApply: (values: Record<string, string>) => void;
}

export default function QuickTemplate({ onApply }: Props) {
  const { t } = useI18n();
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-1.5 text-xs text-[var(--color-text-secondary)] hover:text-[var(--color-accent)] transition-colors"
      >
        <Sparkle size={12} weight="fill" />
        <span>{t("template.title")}</span>
        <CaretDown
          size={12}
          weight="fill"
          className={`transition-transform ${isOpen ? "rotate-180" : ""}`}
        />
      </button>

      {isOpen && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setIsOpen(false)} />
          <div className="absolute top-full left-0 mt-1 w-56 apple-card p-2 z-50 animate-slide-down">
            {TEMPLATE_PRESETS.map((preset) => (
              <button
                key={preset.id}
                type="button"
                onClick={() => {
                  onApply(preset.values);
                  setIsOpen(false);
                }}
                className="w-full text-left px-3 py-2 rounded-lg hover:bg-[var(--color-surface-secondary)] transition-colors"
              >
                <div className="text-sm font-medium text-[var(--color-text-primary)]">
                  {t(`locale.toggle`) === "中" ? preset.nameEn : preset.name}
                </div>
                <div className="text-[12px] text-[var(--color-text-tertiary)] mt-0.5">
                  {preset.scene} · {preset.videoType}
                </div>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
