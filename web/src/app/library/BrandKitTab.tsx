"use client";

import { useEffect, useMemo, useState } from "react";
import { UploadSimple, Image as ImageIcon, WarningCircle, ArrowSquareOut } from "@phosphor-icons/react";
import { useI18n } from "@/i18n/I18nProvider";
import { apiFetch, getMediaUrl, isDemoMode } from "@/components/api";
import EmptyState from "@/components/EmptyState";

interface BrandPreset {
  id: string;
  type: "logo" | "color";
  title: string;
  preview?: string;
  textContent?: string;
}

const BRAND_PRESETS: BrandPreset[] = [
  { id: "momcozy-logo", type: "logo", title: "Momcozy Logo", preview: "/brand/momcozy-logo.svg" },
  { id: "momcozy-color", type: "color", title: "Brand Color Guidelines",
    textContent: "Primary: #6A2B3A · Secondary: #B27A7E · Accent: #6B8578" },
];

interface PortfolioFile {
  id: string;
  filename: string;
  path: string;
  category: string;
  kind: string;
  size_bytes: number;
  mime_type: string;
  produced_at: string;
  product_title?: string | null;
  product_slug?: string | null;
  product_brand?: string | null;
  product_source_url?: string | null;
  product_description?: string | null;
  product_price?: string | null;
}

interface ProductGroup {
  brand: string;
  slug: string;
  prettyName: string;
  description: string | null;
  price: string | null;
  sourceUrl: string | null;
  imageCount: number;
  totalBytes: number;
  coverPath: string;
  files: PortfolioFile[];
}

function parsePath(path: string): { brand: string; slug: string } | null {
  const m = path.match(/^brand_assets\/([^/]+)\/([^/]+)\/images\//);
  if (!m) return null;
  return { brand: m[1], slug: m[2] };
}

function prettifySlug(slug: string): string {
  return slug
    .replace(/-/g, " ")
    .replace(/\bmomcozy\b/gi, "Momcozy")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function groupByProduct(files: PortfolioFile[]): ProductGroup[] {
  const map = new Map<string, ProductGroup>();
  for (const f of files) {
    const parsed = parsePath(f.path);
    if (!parsed) continue;
    const key = `${parsed.brand}/${parsed.slug}`;
    const existing = map.get(key);
    if (existing) {
      existing.imageCount += 1;
      existing.totalBytes += f.size_bytes;
      existing.files.push(f);
      if (f.filename.startsWith("01.")) existing.coverPath = f.path;
      if (!existing.description && f.product_description) existing.description = f.product_description;
      if (!existing.price && f.product_price) existing.price = f.product_price;
      if (!existing.sourceUrl && f.product_source_url) existing.sourceUrl = f.product_source_url;
      if (f.product_title) existing.prettyName = f.product_title;
    } else {
      map.set(key, {
        brand: f.product_brand || parsed.brand,
        slug: f.product_slug || parsed.slug,
        prettyName: f.product_title || prettifySlug(parsed.slug),
        description: f.product_description || null,
        price: f.product_price || null,
        sourceUrl: f.product_source_url || null,
        imageCount: 1,
        totalBytes: f.size_bytes,
        coverPath: f.path,
        files: [f],
      });
    }
  }
  return Array.from(map.values()).sort((a, b) => b.imageCount - a.imageCount);
}

function formatBytes(b: number): string {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(0)} KB`;
  return `${(b / (1024 * 1024)).toFixed(1)} MB`;
}

export default function BrandKitTab() {
  const { t } = useI18n();
  const [files, setFiles] = useState<PortfolioFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedSlug, setExpandedSlug] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await apiFetch("/portfolio/?kind=brand_kit&limit=500&sort=recent");
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        const data = await res.json();
        if (!cancelled) setFiles(data.files || []);
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e);
        if (!cancelled) setError(msg);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const productGroups = useMemo(() => groupByProduct(files), [files]);
  const totalImages = files.length;

  const expandedGroup = expandedSlug
    ? productGroups.find((g) => g.slug === expandedSlug)
    : null;

  return (
    <div className="space-y-6">
      <section className="space-y-3">
        <header className="flex items-center justify-between">
          <h3 className="text-[13px] font-semibold text-[var(--text-h1)]">
            {t("library.brand_kit.presets.title")}
          </h3>
          <p className="text-[11px] text-[var(--text-muted)]">
            {BRAND_PRESETS.length} {t("library.brand_kit.presets.suffix")}
          </p>
        </header>
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
          {BRAND_PRESETS.map((item) => (
            <div
              key={item.id}
              data-asset-card
              data-kind="brand_preset"
              className="apple-card overflow-hidden hover:shadow-md transition-all duration-200"
            >
              <div className="aspect-square bg-[var(--bg-panel)] flex items-center justify-center overflow-hidden">
                {item.type === "logo" && item.preview ? (
                  <img src={item.preview} alt={item.title} className="max-w-[60%] max-h-[60%] object-contain" />
                ) : (
                  <div className="w-full h-full flex flex-col">
                    <div className="flex-1" style={{ background: "#6A2B3A" }} />
                    <div className="flex-1" style={{ background: "#B27A7E" }} />
                    <div className="flex-1" style={{ background: "#6B8578" }} />
                  </div>
                )}
              </div>
              <div className="p-4">
                <h4 className="text-[13px] font-medium text-[var(--text-h1)] truncate">{item.title}</h4>
                {item.textContent && (
                  <p className="text-[11px] text-[var(--text-muted)] mt-1 line-clamp-2">{item.textContent}</p>
                )}
                <p className="text-[11px] text-[var(--text-muted)] mt-1.5">
                  {item.type === "logo" ? "Logo" : t("library.brandKitTypeColor")}
                </p>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <header className="flex items-center justify-between">
          <div>
            <h3 className="text-[13px] font-semibold text-[var(--text-h1)]">
              {t("library.brand_kit.gallery.title")}
            </h3>
            <p className="text-[11px] text-[var(--text-muted)] mt-0.5">
              {t("library.brand_kit.gallery.subtitle")}
            </p>
          </div>
          {!loading && !error && totalImages > 0 && (
            <p className="text-[11px] text-[var(--text-muted)]">
              {productGroups.length} {t("library.brand_kit.gallery.productSuffix")} · {totalImages} {t("library.brand_kit.gallery.imageSuffix")}
            </p>
          )}
        </header>

        {error && (
          <div className="apple-card p-3 border-l-4 border-[var(--crimson-mist)] bg-[rgba(196,91,80,0.08)] flex items-center gap-2">
            <WarningCircle size={16} weight="fill" className="text-[var(--crimson-mist)] shrink-0" />
            <span className="text-xs text-[var(--crimson-mist)] font-medium">
              {t("library.brand_kit.gallery.fetchError")}: {error}
            </span>
          </div>
        )}

        {loading && (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
            {Array.from({ length: 8 }).map((_, i) => (
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

        {!loading && !error && productGroups.length === 0 && (
          <EmptyState
            illustration="brand-kit"
            title={t("library.brand_kit.gallery.empty")}
            description={t("library.brand_kit.gallery.emptyHint")}
            action={
              <button
                disabled={isDemoMode()}
                className="apple-btn apple-btn-primary text-xs py-2 px-3 disabled:opacity-50"
              >
                <UploadSimple size={14} weight="fill" />
                {t("brand.create")}
              </button>
            }
          />
        )}

        {!loading && !error && productGroups.length > 0 && (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
            {productGroups.map((g) => (
              <button
                key={`${g.brand}/${g.slug}`}
                data-asset-card
                data-kind="brand_kit"
                data-brand={g.brand}
                data-slug={g.slug}
                onClick={() => setExpandedSlug(g.slug)}
                className="apple-card overflow-hidden hover:shadow-md transition-all duration-200 text-left cursor-pointer"
              >
                <div className="aspect-square bg-[var(--bg-panel)] overflow-hidden">
                  <img
                    src={getMediaUrl(g.coverPath)}
                    alt={g.prettyName}
                    className="w-full h-full object-cover"
                    loading="lazy"
                  />
                </div>
                <div className="p-3">
                  <h4 className="text-[12px] font-medium text-[var(--text-h1)] line-clamp-2" title={g.prettyName}>
                    {g.prettyName}
                  </h4>
                  <div className="flex items-center justify-between mt-1.5">
                    <p className="text-[11px] text-[var(--text-muted)] flex items-center gap-1">
                      <ImageIcon size={11} weight="fill" />
                      {g.imageCount} {t("library.brand_kit.gallery.imageSuffix")}
                    </p>
                    {g.price ? (
                      <p className="text-[11px] font-semibold text-[var(--fortune-red)]">{g.price}</p>
                    ) : (
                      <p className="text-[11px] text-[var(--text-muted)]">{formatBytes(g.totalBytes)}</p>
                    )}
                  </div>
                </div>
              </button>
            ))}
          </div>
        )}
      </section>

      {expandedGroup && (
        <div
          className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4"
          onClick={() => setExpandedSlug(null)}
        >
          <div
            className="apple-card max-w-5xl max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <header className="sticky top-0 z-10 px-5 py-4 bg-[var(--bg-card)]/95 backdrop-blur-md border-b border-[var(--border-default)]">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <h4 className="text-[15px] font-semibold text-[var(--text-h1)]">
                    {expandedGroup.prettyName}
                  </h4>
                  <div className="flex items-center gap-3 mt-1 text-[11px] text-[var(--text-muted)]">
                    <span>{expandedGroup.imageCount} {t("library.brand_kit.gallery.imageSuffix")}</span>
                    <span>·</span>
                    <span>{formatBytes(expandedGroup.totalBytes)}</span>
                    {expandedGroup.price && (
                      <>
                        <span>·</span>
                        <span className="font-semibold text-[var(--fortune-red)]">{expandedGroup.price}</span>
                      </>
                    )}
                    <span>·</span>
                    <span>{expandedGroup.brand}</span>
                  </div>
                  {expandedGroup.description && (
                    <p className="text-[12px] text-[var(--text-body)] mt-2 leading-relaxed">
                      {expandedGroup.description}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {expandedGroup.sourceUrl && (
                    <a
                      href={expandedGroup.sourceUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="text-[12px] text-[var(--fortune-red)] flex items-center gap-1 hover:underline"
                    >
                      {t("library.brand_kit.gallery.source")}
                      <ArrowSquareOut size={12} weight="fill" />
                    </a>
                  )}
                  <button
                    onClick={() => setExpandedSlug(null)}
                    className="text-[12px] text-[var(--text-muted)] hover:text-[var(--text-h1)] px-2 py-1"
                    aria-label={t("guide.back")}
                  >
                    ✕
                  </button>
                </div>
              </div>
            </header>
            <div className="p-4 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
              {expandedGroup.files.map((f) => (
                <a
                  key={f.id}
                  href={getMediaUrl(f.path)}
                  target="_blank"
                  rel="noreferrer"
                  className="apple-card overflow-hidden hover:shadow-md transition-all"
                >
                  <div className="aspect-square bg-[var(--bg-panel)]">
                    <img
                      src={getMediaUrl(f.path)}
                      alt={f.filename}
                      className="w-full h-full object-cover"
                      loading="lazy"
                    />
                  </div>
                  <div className="px-2 py-1.5 flex items-center justify-between">
                    <span className="text-[10px] text-[var(--text-muted)]">{f.filename}</span>
                    <span className="text-[10px] text-[var(--text-muted)]">{formatBytes(f.size_bytes)}</span>
                  </div>
                </a>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
