"use client";

import { useEffect, useMemo, useState } from "react";
import { useI18n } from "@/i18n/I18nProvider";
import { TEMPLATE_PRESETS } from "@/demo-data";
import { apiFetch } from "@/components/api";
import type { TemplatePreset } from "@/components/types";
import { CaretDown, Sparkle } from "@phosphor-icons/react";

interface Props {
  scene: string;
  onApply: (values: Record<string, string>) => void;
}

interface BrandPresetsResponse {
  brand: string;
  presets: TemplatePreset[];
  scraped_at: string | null;
}

let _brandPresetsCache: TemplatePreset[] | null | undefined;

async function loadBrandPresets(): Promise<TemplatePreset[] | null> {
  if (_brandPresetsCache !== undefined) return _brandPresetsCache;
  try {
    const res = await apiFetch("/portfolio/brand-presets?brand=momcozy");
    if (!res.ok) {
      _brandPresetsCache = null;
      return null;
    }
    const data: BrandPresetsResponse = await res.json();
    _brandPresetsCache = Array.isArray(data.presets) ? data.presets : [];
    return _brandPresetsCache;
  } catch {
    _brandPresetsCache = null;
    return null;
  }
}

function mergePresets(apiPresets: TemplatePreset[] | null): TemplatePreset[] {
  if (!apiPresets || apiPresets.length === 0) return TEMPLATE_PRESETS;
  const apiIds = new Set(apiPresets.map((p) => p.id));
  const demoOnly = TEMPLATE_PRESETS.filter((p) => !apiIds.has(p.id));
  return [...apiPresets, ...demoOnly];
}

export default function QuickTemplate({ scene, onApply }: Props) {
  const { t, locale } = useI18n();
  const [isOpen, setIsOpen] = useState(false);
  const [livePresets, setLivePresets] = useState<TemplatePreset[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const p = await loadBrandPresets();
      if (!cancelled) setLivePresets(p);
    })();
    return () => { cancelled = true; };
  }, []);

  const filteredPresets = useMemo(() => {
    const all = mergePresets(livePresets);
    return all.filter((p) => p.scene === scene || p.id === "blank");
  }, [livePresets, scene]);

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
          <div
            className="fixed inset-0 z-[55]"
            onClick={() => setIsOpen(false)}
          />
          <div className="absolute top-full right-0 mt-1 w-72 max-h-[60vh] overflow-y-auto apple-card p-2 z-[60] animate-slide-down shadow-xl">
            {filteredPresets.length === 0 ? (
              <div className="px-3 py-4 text-xs text-[var(--color-text-tertiary)] text-center">
                {t("template.empty")}
              </div>
            ) : (
              filteredPresets.map((preset) => (
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
                    {locale === "en" ? preset.nameEn : preset.name}
                  </div>
                  {preset.description && (
                    <div className="text-[11px] text-[var(--color-text-tertiary)] mt-0.5 line-clamp-2">
                      {locale === "en"
                        ? preset.descriptionEn || preset.description
                        : preset.description}
                    </div>
                  )}
                </button>
              ))
            )}
          </div>
        </>
      )}
    </div>
  );
}
