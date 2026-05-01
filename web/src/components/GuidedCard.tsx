"use client";

import React, { useState, useCallback } from "react";
import type { GuidedCard as GuidedCardType } from "./types";
import { useI18n } from "@/i18n/I18nProvider";

interface Props {
  card: GuidedCardType;
  value: string;
  onChange: (fieldKey: string, value: string) => void;
  isFocused: boolean;
  onFocus: () => void;
}

const PRIORITY_STYLES: Record<string, { border: string; badge: string; badgeText: string }> = {
  required: {
    border: "border-l-[3px] border-l-[var(--fortune-red)]",
    badge: "bg-[var(--fortune-red)]",
    badgeText: "text-white",
  },
  recommended: {
    border: "border-l-[3px] border-l-[var(--gold-foil)]",
    badge: "bg-[var(--gold-foil)]",
    badgeText: "text-white",
  },
  optional: {
    border: "border-l-[3px] border-l-[var(--jade-accent)]",
    badge: "bg-[var(--jade-accent)]",
    badgeText: "text-white",
  },
};

export default function GuidedCard({ card, value, onChange, isFocused, onFocus }: Props) {
  const { t } = useI18n();
  const [isExpanded, setIsExpanded] = useState(card.priority !== "optional" || !value);
  const [isCompleted] = useState(!!value && value.trim().length > 0);

  const styles = PRIORITY_STYLES[card.priority] || PRIORITY_STYLES.required;

  const handleChange = useCallback(
    (newValue: string) => {
      onChange(card.fieldKey, newValue);
    },
    [card.fieldKey, onChange]
  );

  const toggleExpand = useCallback(() => {
    setIsExpanded((prev) => !prev);
    onFocus();
  }, [onFocus]);

  const renderInput = () => {
    switch (card.inputType) {
      case "textarea":
        return (
          <textarea
            value={value}
            onChange={(e) => handleChange(e.target.value)}
            placeholder={card.placeholder ? t(card.placeholder) : undefined}
            maxLength={card.maxLength}
            className="apple-input resize-none text-sm"
            rows={3}
          />
        );

      case "select":
        return (
          <select
            value={value}
            onChange={(e) => handleChange(e.target.value)}
            className="apple-input text-sm"
          >
            <option value="">{t("sceneForm.categoryPlaceholder")}</option>
            {(card.options || []).map((opt) => (
              <option key={opt} value={opt}>
                {t(`sceneForm.category${opt.charAt(0).toUpperCase() + opt.slice(1)}`) || opt}
              </option>
            ))}
          </select>
        );

      case "multiselect":
        return (
          <div className="flex flex-wrap gap-1.5">
            {(card.options || []).map((opt) => {
              const selected = value.split(",").includes(opt);
              return (
                <button
                  key={opt}
                  type="button"
                  onClick={() => {
                    const current = value ? value.split(",") : [];
                    const next = selected
                      ? current.filter((v) => v !== opt)
                      : [...current, opt];
                    handleChange(next.join(","));
                  }}
                  className={`apple-pill text-xs ${selected ? "active" : ""}`}
                >
                  {opt}
                </button>
              );
            })}
          </div>
        );

      case "toggle":
        return (
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => handleChange(value === "true" ? "false" : "true")}
              className={`relative w-11 h-6 rounded-full transition-colors ${
                value === "true" ? "bg-[var(--fortune-red)]" : "bg-[var(--border-default)]"
              }`}
            >
              <span
                className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform ${
                  value === "true" ? "translate-x-5" : ""
                }`}
              />
            </button>
            <span className="text-sm text-[var(--color-text-secondary)]">
              {value === "true" ? t("sceneForm.keepOriginalAudio") : "AI 配音"}
            </span>
          </div>
        );

      case "duration":
        return (
          <div className="flex gap-2">
            {["15s", "30s", "45s", "60s"].map((d) => (
              <button
                key={d}
                type="button"
                onClick={() => handleChange(d)}
                className={`flex-1 py-2 rounded-xl text-xs font-medium transition-all ${
                  value === d
                    ? "bg-[var(--color-accent)] text-white shadow-sm"
                    : "bg-[var(--color-bg)] text-[var(--color-text-secondary)] border border-[var(--color-border-light)]"
                }`}
              >
                {d}
              </button>
            ))}
          </div>
        );

      case "image-upload":
      case "video-upload":
        return (
          <div className="border-2 border-dashed border-[var(--color-border-light)] rounded-xl p-6 text-center hover:border-[var(--color-accent)] transition-colors cursor-pointer">
            <div className="text-2xl mb-2">{card.inputType === "image-upload" ? "🖼️" : "🎬"}</div>
            <p className="text-sm text-[var(--color-text-tertiary)]">
              {t("upload.dragInactive")}
            </p>
            <p className="text-xs text-[var(--color-text-tertiary)] mt-1">
              {t("upload.hint")}
            </p>
          </div>
        );

      default:
        return (
          <input
            type="text"
            value={value}
            onChange={(e) => handleChange(e.target.value)}
            placeholder={card.placeholder ? t(card.placeholder) : undefined}
            maxLength={card.maxLength}
            className="apple-input text-sm"
          />
        );
    }
  };

  // 折叠态：显示一行摘要
  if (!isExpanded && isCompleted) {
    return (
      <div
        onClick={toggleExpand}
        className={`apple-card p-3 cursor-pointer hover:shadow-md transition-all ${styles.border} opacity-70 hover:opacity-100`}
      >
        <div className="flex items-center gap-2">
          <span className="text-sm">{card.stepIcon}</span>
          <span className="text-xs font-medium text-[var(--color-text-secondary)]">
            {card.stepName}
          </span>
          <span className="text-xs text-[var(--color-text-tertiary)] truncate flex-1">
            {value}
          </span>
          <span className="text-xs text-[var(--jade-accent)]">✓</span>
        </div>
      </div>
    );
  }

  return (
    <div
      onClick={onFocus}
      className={`apple-card p-4 transition-all ${styles.border} ${
        isFocused ? "ring-1 ring-[var(--color-accent)]/20 shadow-md" : ""
      }`}
    >
      {/* 优先级标签 + 步骤名 */}
      <div className="flex items-center gap-2 mb-3">
        <span
          className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${styles.badge} ${styles.badgeText}`}
        >
          {t(`card.priority.${card.priority}`)}
        </span>
        <span className="text-lg">{card.stepIcon}</span>
        <span className="text-xs font-medium text-[var(--color-text-secondary)]">
          {card.stepName}
        </span>
      </div>

      {/* 引导问题 */}
      <h4 className="text-sm font-medium text-[var(--color-text-primary)] mb-1.5">
        {card.question}
      </h4>

      {/* 原因说明 */}
      <p className="text-xs text-[var(--color-text-tertiary)] mb-3 leading-relaxed">
        {card.reason}
      </p>

      {/* 输入区域 */}
      <div onClick={(e) => e.stopPropagation()}>{renderInput()}</div>

      {/* 字数提示（textarea 且有 maxLength） */}
      {card.inputType === "textarea" && card.maxLength && (
        <div className="text-right mt-1">
          <span className="text-[11px] text-[var(--color-text-tertiary)]">
            {value.length} / {card.maxLength}
          </span>
        </div>
      )}
    </div>
  );
}
