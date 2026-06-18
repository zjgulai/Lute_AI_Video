"use client";

import { type KeyboardEvent, useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
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
    const res = await apiFetch("/portfolio/brand-presets?brand=momcozy", {
      suppressAuthExpiryRedirect: true,
    });
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
  const menuId = useId();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [livePresets, setLivePresets] = useState<TemplatePreset[] | null>(null);

  const closeMenu = useCallback((restoreFocus = true) => {
    setIsOpen(false);
    if (restoreFocus) {
      requestAnimationFrame(() => triggerRef.current?.focus());
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const p = await loadBrandPresets();
      if (!cancelled) setLivePresets(p);
    })();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      closeMenu();
    };

    document.addEventListener("keydown", handleKeyDown);
    requestAnimationFrame(() => itemRefs.current[0]?.focus());

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [closeMenu, isOpen]);

  const filteredPresets = useMemo(() => {
    const all = mergePresets(livePresets);
    return all.filter((p) => p.scene === scene || p.id === "blank");
  }, [livePresets, scene]);

  const focusPreset = (index: number) => {
    const next = itemRefs.current[index];
    if (next) next.focus();
  };

  const handlePresetKeyDown = (index: number, event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      focusPreset((index + 1) % filteredPresets.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      focusPreset((index - 1 + filteredPresets.length) % filteredPresets.length);
    } else if (event.key === "Home") {
      event.preventDefault();
      focusPreset(0);
    } else if (event.key === "End") {
      event.preventDefault();
      focusPreset(filteredPresets.length - 1);
    }
  };

  return (
    <div className="relative">
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setIsOpen((open) => !open)}
        aria-haspopup="menu"
        aria-expanded={isOpen}
        aria-controls={isOpen ? menuId : undefined}
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
            onClick={() => closeMenu()}
          />
          <div
            id={menuId}
            role="menu"
            aria-label={t("template.title")}
            className="absolute top-full right-0 mt-1 w-72 max-h-[60vh] overflow-y-auto apple-card p-2 z-[60] animate-slide-down shadow-xl"
          >
            {filteredPresets.length === 0 ? (
              <div className="px-3 py-4 text-xs text-[var(--color-text-tertiary)] text-center">
                {t("template.empty")}
              </div>
            ) : (
              filteredPresets.map((preset, index) => (
                <button
                  ref={(node) => {
                    itemRefs.current[index] = node;
                  }}
                  key={preset.id}
                  type="button"
                  role="menuitem"
                  onKeyDown={(event) => handlePresetKeyDown(index, event)}
                  onClick={() => {
                    onApply(preset.values);
                    closeMenu();
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
