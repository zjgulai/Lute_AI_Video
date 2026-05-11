"use client";

import React from "react";
import type { ModelProfile } from "./types";
import { useI18n } from "@/i18n/I18nProvider";

interface Props {
  models: ModelProfile[];
  selected: string[];
  onChange: (ids: string[]) => void;
  emptyLabel?: string;
}

export default function VlogModelSelector({
  models,
  selected,
  onChange,
  emptyLabel,
}: Props) {
  const { t } = useI18n();
  const resolvedEmptyLabel = emptyLabel ?? t("vlog.modelsEmpty");
  const toggleModel = (id: string) => {
    if (selected.includes(id)) {
      onChange(selected.filter((s) => s !== id));
    } else {
      onChange([...selected, id]);
    }
  };

  return (
    <div className="space-y-4">
      {/* Model grid */}
      <div className="grid grid-cols-4 gap-3">
        {models.map((model) => {
          const isSelected = selected.includes(model.id);
          return (
            <button
              key={model.id}
              onClick={() => toggleModel(model.id)}
              className={`apple-card overflow-hidden text-left transition-all duration-200 cursor-pointer ${
                isSelected
                  ? "ring-2 ring-[var(--color-accent)] ring-offset-1 shadow-md"
                  : "hover:shadow-sm"
              }`}
            >
              {/* Portrait placeholder */}
              <div
                className="h-28 relative overflow-hidden"
                style={{
                  background: `linear-gradient(135deg, ${model.gradient[0]} 0%, ${model.gradient[1]} 100%)`,
                }}
              >
                {/* Abstract portrait circles */}
                <div className="absolute w-14 h-14 rounded-full bg-white/80 left-1/2 top-5 -translate-x-1/2 shadow-md" />
                <div className="absolute w-20 h-24 rounded-t-full bg-white/75 left-1/2 -bottom-6 -translate-x-1/2 shadow-sm" />
                {/* Initials badge */}
                <div className="absolute right-2 top-2 px-1.5 py-0.5 rounded-full bg-white/15 text-white text-[12px] font-bold backdrop-blur-sm">
                  {model.role.slice(0, 2).toUpperCase()}
                </div>
              </div>
              {/* Info */}
              <div className="p-2.5 space-y-1">
                <div className="text-xs font-semibold text-[var(--color-text-primary)]">
                  {model.name}
                </div>
                <div className="inline-block px-1.5 py-0.5 rounded-full bg-[var(--color-bg)] text-[12px] font-medium text-[var(--color-text-secondary)]">
                  {model.role}
                </div>
                <div className="text-[12px] text-[var(--color-text-tertiary)] leading-relaxed">
                  {model.description}
                </div>
              </div>
            </button>
          );
        })}
      </div>

      {/* Selected models list */}
      {selected.length > 0 ? (
        <div className="flex flex-wrap gap-2 p-3 rounded-xl bg-[var(--color-bg)] border border-[var(--color-border-light)]">
          {models
            .filter((m) => selected.includes(m.id))
            .map((m) => (
              <div
                key={m.id}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-white border border-[var(--color-border-light)] text-[12px]"
              >
                <span className="font-medium text-[var(--color-text-primary)]">
                  {m.name}
                </span>
                <span className="text-[var(--color-text-tertiary)]">{m.role}</span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    toggleModel(m.id);
                  }}
                  className="ml-0.5 w-4 h-4 rounded-full bg-[var(--color-border-light)] hover:bg-red-100 flex items-center justify-center text-[12px] text-[var(--color-text-tertiary)] hover:text-red-500 transition-colors cursor-pointer"
                >
                  ×
                </button>
              </div>
            ))}
        </div>
      ) : (
        <div className="p-6 rounded-xl border border-dashed border-[var(--color-border)] bg-[var(--color-bg)] text-center">
          <p className="text-xs text-[var(--color-text-tertiary)]">{resolvedEmptyLabel}</p>
        </div>
      )}
    </div>
  );
}
