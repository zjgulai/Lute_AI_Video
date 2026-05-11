"use client";

import { useEffect, useState } from "react";
import { UploadSimple, Image as ImageIcon, Article, WarningCircle } from "@phosphor-icons/react";
import { useI18n } from "@/i18n/I18nProvider";
import { isDemoMode } from "@/components/api";
import EmptyState from "@/components/EmptyState";

interface BrandKitItem {
  id: string;
  type: "logo" | "color" | "voice" | "font";
  title: string;
  preview?: string;
  textContent?: string;
  updatedAt: string;
}

const PRESET_KIT: BrandKitItem[] = [
  {
    id: "momcozy-logo",
    type: "logo",
    title: "Momcozy Logo",
    preview: "/brand/momcozy-logo.svg",
    updatedAt: new Date().toISOString(),
  },
  {
    id: "momcozy-color",
    type: "color",
    title: "Brand Color Guidelines",
    textContent: "Primary: #6A2B3A · Secondary: #B27A7E · Accent: #6B8578",
    updatedAt: new Date().toISOString(),
  },
];

export default function BrandKitTab() {
  const { t } = useI18n();
  const [items, setItems] = useState<BrandKitItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setItems(PRESET_KIT);
    setLoading(false);
  }, []);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-[12px] text-[var(--text-muted)]">
            {items.length} {t("library.brandKitCountSuffix")}
          </p>
        </div>
        <button
          disabled={isDemoMode()}
          className="apple-btn apple-btn-primary text-xs py-2 px-3 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <UploadSimple size={14} weight="fill" />
          {t("brand.create")}
        </button>
      </div>

      {error && (
        <div className="apple-card p-3 border-l-4 border-[var(--crimson-mist)] bg-[rgba(196,91,80,0.08)] flex items-center gap-2">
          <WarningCircle size={16} weight="fill" className="text-[var(--crimson-mist)] shrink-0" />
          <span className="text-xs text-[var(--crimson-mist)] font-medium">{error}</span>
        </div>
      )}

      {loading && (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="apple-card overflow-hidden">
              <div className="aspect-square skeleton" />
              <div className="p-4 space-y-2">
                <div className="h-3 skeleton w-3/4" />
                <div className="h-2 skeleton w-1/2" />
              </div>
            </div>
          ))}
        </div>
      )}

      {!loading && items.length === 0 && (
        <EmptyState
          illustration="brand-kit"
          title={t("brand.empty")}
          description={t("brand.emptyHint")}
          action={
            <button
              data-empty-cta
              disabled={isDemoMode()}
              className="apple-btn apple-btn-primary text-xs py-2 px-3 disabled:opacity-50"
            >
              <UploadSimple size={14} weight="fill" />
              {t("brand.create")}
            </button>
          }
        />
      )}

      {!loading && items.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
          {items.map((item) => (
            <div
              key={item.id}
              data-asset-card
              data-kind="brand_kit"
              className="apple-card overflow-hidden hover:shadow-md transition-all duration-200"
            >
              <div className="aspect-square bg-[var(--bg-panel)] flex items-center justify-center overflow-hidden">
                {item.type === "logo" && item.preview ? (
                  <img src={item.preview} alt={item.title} className="max-w-[60%] max-h-[60%] object-contain" />
                ) : item.type === "color" ? (
                  <div className="w-full h-full flex flex-col">
                    <div className="flex-1" style={{ background: "#6A2B3A" }} />
                    <div className="flex-1" style={{ background: "#B27A7E" }} />
                    <div className="flex-1" style={{ background: "#6B8578" }} />
                  </div>
                ) : item.type === "voice" ? (
                  <Article size={32} weight="fill" className="text-[var(--cinema-violet)]" />
                ) : (
                  <ImageIcon size={32} weight="fill" className="text-[var(--text-muted)]" />
                )}
              </div>
              <div className="p-4">
                <h3 className="text-[13px] font-medium text-[var(--text-h1)] truncate">{item.title}</h3>
                {item.textContent && (
                  <p className="text-[11px] text-[var(--text-muted)] mt-1 line-clamp-2">{item.textContent}</p>
                )}
                <p className="text-[11px] text-[var(--text-muted)] mt-1.5">
                  {item.type === "logo" && "Logo"}
                  {item.type === "color" && t("library.brandKitTypeColor")}
                  {item.type === "voice" && "Brand Voice"}
                  {item.type === "font" && t("library.brandKitTypeFont")}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
