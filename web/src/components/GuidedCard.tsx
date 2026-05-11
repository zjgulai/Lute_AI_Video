"use client";

import React, { useState, useCallback, useRef } from "react";
import type { GuidedCard as GuidedCardType } from "./types";
import { useI18n } from "@/i18n/I18nProvider";
import { apiFetch } from "./api";
import AssetPickerModal, { type AcceptKind } from "./AssetPickerModal";
import { Folder } from "@phosphor-icons/react";

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
  const [uploading, setUploading] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

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

  const handleUpload = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      setUploading(true);
      try {
        const formData = new FormData();
        formData.append("file", file);
        const res = await apiFetch("/api/upload", {
          method: "POST",
          body: formData,
        });
        if (res.ok) {
          const data = await res.json();
          handleChange(data.path || data.filename || file.name);
        } else {
          console.error("Upload failed", res.status);
        }
      } catch (err) {
        console.error("Upload error", err);
      } finally {
        setUploading(false);
      }
    },
    [handleChange]
  );

  const renderInput = () => {
    const fieldId = `guided-${card.fieldKey}`;
    const hintId = `${fieldId}-hint`;
    const requiredProp = card.priority === "required" ? { "aria-required": "true" as const } : {};

    switch (card.inputType) {
      case "textarea":
        return (
          <textarea
            id={fieldId}
            name={card.fieldKey}
            value={value}
            onChange={(e) => handleChange(e.target.value)}
            placeholder={card.placeholder ? t(card.placeholder) : undefined}
            maxLength={card.maxLength}
            aria-describedby={hintId}
            {...requiredProp}
            className="apple-input resize-none text-sm"
            rows={3}
          />
        );

      case "select":
        return (
          <select
            id={fieldId}
            name={card.fieldKey}
            value={value}
            onChange={(e) => handleChange(e.target.value)}
            aria-describedby={hintId}
            {...requiredProp}
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
          <div
            id={fieldId}
            role="group"
            aria-label={card.stepName}
            aria-describedby={hintId}
            className="flex flex-wrap gap-1.5"
          >
            {(card.options || []).map((opt) => {
              const selected = value.split(",").includes(opt);
              return (
                <button
                  key={opt}
                  type="button"
                  role="checkbox"
                  aria-checked={selected}
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
              id={fieldId}
              type="button"
              role="switch"
              aria-checked={value === "true"}
              aria-label={card.stepName}
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
              {value === "true" ? t("sceneForm.keepOriginalAudio") : t("sceneForm.aiVoiceover")}
            </span>
          </div>
        );

      case "duration":
        return (
          <div
            id={fieldId}
            role="radiogroup"
            aria-label={card.stepName}
            aria-describedby={hintId}
            className="flex gap-2"
          >
            {["15s", "30s", "45s", "60s"].map((d) => (
              <button
                key={d}
                type="button"
                role="radio"
                aria-checked={value === d}
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
          <div className="space-y-2">
            <div
              onClick={() => !uploading && fileInputRef.current?.click()}
              className={`border-2 border-dashed rounded-xl p-6 text-center transition-colors cursor-pointer ${
                value
                  ? "border-[var(--jade-accent)] bg-[rgba(120,175,140,0.05)]"
                  : "border-[var(--color-border-light)] hover:border-[var(--color-accent)]"
              } ${uploading ? "opacity-60 cursor-wait" : ""}`}
            >
              <div className="text-2xl mb-2">{card.inputType === "image-upload" ? "🖼️" : "🎬"}</div>
              <p className="text-sm text-[var(--color-text-tertiary)]">
                {uploading
                  ? t("upload.uploading")
                  : value
                  ? value.split("/").pop()
                  : t("upload.dragInactive")}
              </p>
              <p className="text-xs text-[var(--color-text-tertiary)] mt-1">
                {t("upload.hint")}
              </p>
            </div>
            <input
              ref={fileInputRef}
              id={fieldId}
              name={card.fieldKey}
              type="file"
              className="hidden"
              accept={card.inputType === "image-upload" ? "image/*" : "video/*"}
              aria-label={card.stepName}
              aria-describedby={hintId}
              {...requiredProp}
              onChange={handleUpload}
            />
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => setPickerOpen(true)}
                className="flex items-center gap-1.5 text-[12px] text-[var(--color-accent)] hover:opacity-80 transition-opacity"
              >
                <Folder size={12} weight="fill" />
                {t("picker.fromLibrary")}
              </button>
              {value && (
                <button
                  type="button"
                  onClick={() => handleChange("")}
                  className="text-[12px] text-[var(--text-muted)] hover:text-[var(--fortune-red)] transition-colors"
                >
                  {t("upload.clear")}
                </button>
              )}
            </div>
            {pickerOpen && (
              <AssetPickerModal
                acceptKind={(card.inputType === "image-upload" ? "image" : "video") as AcceptKind}
                onPick={(urls) => {
                  if (urls.length > 0) handleChange(urls[0]);
                }}
                onClose={() => setPickerOpen(false)}
              />
            )}
          </div>
        );

      default:
        return (
          <input
            id={fieldId}
            name={card.fieldKey}
            type="text"
            value={value}
            onChange={(e) => handleChange(e.target.value)}
            placeholder={card.placeholder ? t(card.placeholder) : undefined}
            maxLength={card.maxLength}
            aria-describedby={hintId}
            {...requiredProp}
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
          className={`text-[12px] font-semibold px-2 py-0.5 rounded-full ${styles.badge} ${styles.badgeText}`}
        >
          {t(`card.priority.${card.priority}`)}
        </span>
        <span className="text-lg">{card.stepIcon}</span>
        <span className="text-xs font-medium text-[var(--color-text-secondary)]">
          {card.stepName}
        </span>
      </div>

      {/* 引导问题 — semantic <label> tied to the input via htmlFor */}
      <label
        htmlFor={`guided-${card.fieldKey}`}
        className="block text-sm font-medium text-[var(--color-text-primary)] mb-1.5 cursor-pointer"
      >
        {card.question}
        {card.priority === "required" && (
          <span aria-label="required" className="ml-1 text-[var(--fortune-red)] font-semibold">
            *
          </span>
        )}
      </label>

      {/* 原因说明 */}
      <p
        id={`guided-${card.fieldKey}-hint`}
        className="text-xs text-[var(--color-text-tertiary)] mb-3 leading-relaxed"
      >
        {card.reason}
      </p>

      {/* 输入区域 */}
      <div onClick={(e) => e.stopPropagation()}>{renderInput()}</div>

      {/* 字数提示（textarea 且有 maxLength） */}
      {card.inputType === "textarea" && card.maxLength && (
        <div className="text-right mt-1">
          <span className="text-[12px] text-[var(--color-text-tertiary)]">
            {value.length} / {card.maxLength}
          </span>
        </div>
      )}
    </div>
  );
}
