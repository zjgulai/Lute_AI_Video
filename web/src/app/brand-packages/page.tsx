"use client";

import { useState, useEffect, useMemo, useCallback } from "react";
import { useI18n } from "@/i18n/I18nProvider";
import { isDemoMode, fetchAssets, getMediaUrl } from "@/components/api";
import Link from "next/link";
import {
  Package,
  MagnifyingGlass,
  Sparkle,
  UploadSimple,
  FolderOpen,
  Image,
  VideoCamera,
  MusicNotes,
  Article,
  Palette,
  Camera,
  Spinner,
  WarningCircle,
  X,
  CheckCircle,
} from "@phosphor-icons/react";
import AssetCard, { AssetItem, AssetType, AssetSource } from "@/components/AssetCard";

// ── Category Tree ──

interface Category {
  id: string;
  labelKey: string;
  icon: React.ComponentType<any>;
  /** Which AssetType values this category includes */
  assetTypes: AssetType[];
  /** Which AssetSource values this category includes (empty = all) */
  sources: AssetSource[];
  /** Special flag for gallery/finished works */
  galleryOnly?: boolean;
}

const CATEGORIES: Category[] = [
  {
    id: "all",
    labelKey: "brand.category.all",
    icon: FolderOpen,
    assetTypes: ["video", "image", "audio", "text"],
    sources: [],
  },
  {
    id: "brand_identity",
    labelKey: "brand.category.identity",
    icon: Palette,
    assetTypes: ["video", "image", "audio", "text"],
    sources: ["imported"],
  },
  {
    id: "ai_produced",
    labelKey: "brand.category.aiProduced",
    icon: Sparkle,
    assetTypes: ["video", "image", "audio", "text"],
    sources: ["ai"],
  },
  {
    id: "original",
    labelKey: "brand.category.original",
    icon: Camera,
    assetTypes: ["video", "image", "audio", "text"],
    sources: ["manual"],
  },
  {
    id: "finished",
    labelKey: "brand.category.finished",
    icon: CheckCircle,
    assetTypes: ["video"],
    sources: ["ai"],
    galleryOnly: true,
  },
];

// ── Type Guards ──

function isAssetType(v: string): v is AssetType {
  return v === "video" || v === "image" || v === "audio" || v === "text";
}

function isAssetSource(v: string): v is AssetSource {
  return v === "ai" || v === "manual" || v === "imported";
}

// ── MIME Type → AssetType ──

function mimeTypeToAssetType(mimeType: string): AssetType {
  if (mimeType.startsWith("video/")) return "video";
  if (mimeType.startsWith("image/")) return "image";
  if (mimeType.startsWith("audio/")) return "audio";
  if (mimeType.startsWith("text/")) return "text";
  // Fallbacks by extension
  const lower = mimeType.toLowerCase();
  if (lower.includes("json") || lower.includes("yaml") || lower.includes("xml")) return "text";
  if (lower.includes("script") || lower.includes("prompt")) return "text";
  return "text";
}

// ── File Path → AssetSource ──

function inferSourceFromPath(filePath: string, mimeType: string, tags?: string[]): AssetSource {
  const lower = filePath.toLowerCase();
  // Check tags first (most explicit)
  if (tags) {
    const tagStr = tags.join(" ").toLowerCase();
    if (tagStr.includes("ai-") || tagStr.includes("seedance") || tagStr.includes("generated")) return "ai";
    if (tagStr.includes("upload") || tagStr.includes("manual")) return "manual";
    if (tagStr.includes("brand") || tagStr.includes("imported")) return "imported";
  }
  // Path-based inference
  if (lower.includes("/portfolio/") || lower.includes("/ai/") || lower.includes("/generated/")) return "ai";
  if (lower.includes("/upload/") || lower.includes("/uploads/") || lower.includes("/manual/")) return "manual";
  if (lower.includes("/brand/") || lower.includes("/identity/")) return "imported";
  // Default: if it looks like a media generation output, mark as ai
  if (lower.includes("seedance") || lower.includes("poyo") || lower.includes("clip")) return "ai";
  // Conservative fallback: manual upload
  return "manual";
}

// ── Backend File → AssetItem ──

interface BackendFile {
  filename?: string;
  path?: string;
  file_path?: string;
  size?: number;
  mime_type?: string;
  type?: string;
  created?: number;
  created_at?: string;
  label?: string;
  original_name?: string;
  tags?: string[];
  metadata?: Record<string, any>;
  duration?: number;
}

function backendFileToAssetItem(file: BackendFile): AssetItem | null {
  const filePath = file.file_path || file.path || "";
  const filename = file.filename || file.original_name || file.label || "";
  if (!filePath && !filename) return null;

  const mimeType = file.mime_type || "";
  const assetType = mimeType ? mimeTypeToAssetType(mimeType) : (file.type as AssetType) || "text";
  const source = inferSourceFromPath(filePath, mimeType, file.tags);
  const title = file.label || file.original_name || file.filename || "Untitled";
  const createdAt = file.created_at
    ? new Date(file.created_at).toISOString()
    : file.created
      ? new Date(file.created * 1000).toISOString()
      : new Date().toISOString();

  // Determine thumbnail for videos/images
  let thumbnail: string | undefined;
  if (assetType === "video" || assetType === "image") {
    thumbnail = filePath;
  }

  return {
    id: `file-${filePath}-${file.created || Date.now()}`,
    type: assetType,
    source,
    title,
    thumbnail,
    filePath,
    duration: file.duration || file.metadata?.duration || 0,
    createdAt,
    metadata: {
      ...file.metadata,
      tags: file.tags || [],
      size: file.size,
      mimeType,
    },
  };
}

// ── Load Gallery Assets (from localStorage) ──

function loadGalleryAssets(): AssetItem[] {
  try {
    const stored = localStorage.getItem("hermes_gallery_items");
    if (!stored) return [];
    const items = JSON.parse(stored);
    return items.map((item: any) => ({
      id: `gallery-${item.id}`,
      type: "video" as AssetType,
      source: "ai" as AssetSource,
      title: item.title || "Untitled",
      thumbnail: item.thumbnail,
      filePath: item.videoPath,
      duration: item.duration || 0,
      createdAt: item.createdAt || new Date().toISOString(),
      metadata: {
        gallery: true,
        scene: item.scene,
        videoType: item.videoType,
        score: item.score,
      },
    }));
  } catch {
    return [];
  }
}

// ── Load Brand Packages (hardcoded fallback + API-ready structure) ──

function loadBrandPackages(): AssetItem[] {
  return [
    {
      id: "brand-logo",
      type: "image",
      source: "imported",
      title: "Momcozy Logo",
      thumbnail: "/brand/momcozy-logo.svg",
      filePath: "/brand/momcozy-logo.svg",
      createdAt: new Date().toISOString(),
      metadata: { tags: ["logo", "brand-identity"] },
    },
    {
      id: "brand-color",
      type: "text",
      source: "imported",
      title: "Brand Color Guidelines",
      textContent: "Primary: #6A2B3A · Secondary: #B27A7E · Accent: #6B8578",
      createdAt: new Date().toISOString(),
      metadata: { tags: ["color", "brand-guidelines"] },
    },
  ];
}

// ── Demo Assets → AssetItem ──

function demoAssetsToItems(demoAssets: any[]): AssetItem[] {
  return demoAssets.map((a, i) => {
    const type = a.mime_type?.startsWith("video/")
      ? "video"
      : a.mime_type?.startsWith("image/")
        ? "image"
        : a.type || "text";
    const isAi = a.tags?.some((t: string) => t.includes("ai-") || t.includes("seedance"));
    return {
      id: `demo-${i}-${a.filename}`,
      type: type as AssetType,
      source: (isAi ? "ai" : "manual") as AssetSource,
      title: a.label || a.original_name || a.filename || "Untitled",
      thumbnail: a.type === "video" || a.type === "image" ? a.path : undefined,
      filePath: a.path,
      duration: a.metadata?.duration || a.duration || 0,
      createdAt: a.metadata?.uploaded_at || new Date(a.created * 1000).toISOString(),
      metadata: {
        tags: a.tags || [],
        platform: a.platform,
        size: a.file_size || a.size,
        demo: true,
      },
    };
  });
}

// ── Page ──

export default function BrandPackagesPage() {
  const { t } = useI18n();
  const [activeCategory, setActiveCategory] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [sourceFilter, setSourceFilter] = useState<AssetSource | "all">("all");
  const [assets, setAssets] = useState<AssetItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAllAssets = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const allAssets: AssetItem[] = [];

      // 1. Gallery items (finished videos from localStorage)
      const gallery = loadGalleryAssets();
      allAssets.push(...gallery);

      // 2. Brand packages (hardcoded fallback)
      const brand = loadBrandPackages();
      allAssets.push(...brand);

      if (isDemoMode()) {
        // 3. Demo mode: load mock footage assets
        try {
          const { DEMO_FOOTAGE_ASSETS, DEMO_ASSETS } = await import("@/demo-data");
          const demoFootage = (DEMO_FOOTAGE_ASSETS || []).map((a: any, i: number) => ({
            id: `demo-footage-${i}`,
            type: (a.mime_type?.startsWith("video/") ? "video" : "image") as AssetType,
            source: "manual" as AssetSource,
            title: a.original_name || a.filename || "Untitled",
            thumbnail: a.file_path,
            filePath: a.file_path,
            duration: a.metadata?.duration || 0,
            createdAt: a.metadata?.uploaded_at || new Date().toISOString(),
            metadata: { tags: a.tags || [], demo: true },
          }));
          allAssets.push(...demoFootage);

          // Also add DEMO_ASSETS as AI-produced
          const demoAi = demoAssetsToItems(DEMO_ASSETS || []);
          allAssets.push(...demoAi);
        } catch {
          // ignore demo data import errors
        }
      } else {
        // 3. Real mode: call backend API
        try {
          const files = await fetchAssets();
          const mapped = (files || [])
            .map(backendFileToAssetItem)
            .filter((item): item is AssetItem => item !== null);
          allAssets.push(...mapped);
        } catch (apiErr: any) {
          console.error("[BrandAssets] API fetch failed:", apiErr);
          // Non-blocking: still show gallery + brand packages
          setError(t("brand.apiFetchHint") || "后端连接失败，显示本地数据");
        }
      }

      // Deduplicate by id
      const seen = new Set<string>();
      const deduped = allAssets.filter((a) => {
        if (seen.has(a.id)) return false;
        seen.add(a.id);
        return true;
      });

      setAssets(deduped);
    } catch (e: any) {
      setError(e.message || t("common.fetchFailed"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    fetchAllAssets();
  }, [fetchAllAssets]);

  // Filter assets by category, source, and search
  const filteredAssets = useMemo(() => {
    const category = CATEGORIES.find((c) => c.id === activeCategory);

    return assets.filter((asset) => {
      // Category filter
      if (category) {
        // Type check
        if (!category.assetTypes.includes(asset.type)) return false;
        // Source check
        if (category.sources.length > 0 && !category.sources.includes(asset.source)) return false;
        // Gallery-only check (finished videos)
        if (category.galleryOnly && !asset.metadata?.gallery) return false;
      }

      // Source filter
      if (sourceFilter !== "all" && asset.source !== sourceFilter) return false;

      // Search filter
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        return (
          asset.title.toLowerCase().includes(q) ||
          (asset.textContent?.toLowerCase().includes(q) ?? false) ||
          asset.metadata?.tags?.some((tag: string) => tag.toLowerCase().includes(q))
        );
      }

      return true;
    });
  }, [assets, activeCategory, sourceFilter, searchQuery]);

  // Count assets per category (for sidebar badges)
  const categoryCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const cat of CATEGORIES) {
      counts[cat.id] = assets.filter((asset) => {
        if (!cat.assetTypes.includes(asset.type)) return false;
        if (cat.sources.length > 0 && !cat.sources.includes(asset.source)) return false;
        if (cat.galleryOnly && !asset.metadata?.gallery) return false;
        return true;
      }).length;
    }
    return counts;
  }, [assets]);

  const activeLabel = CATEGORIES.find((c) => c.id === activeCategory)?.labelKey || "brand.category.all";

  return (
    <div className="min-h-screen bg-[var(--color-bg)]">
      <div className="max-w-6xl mx-auto px-4 py-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <Link
              href="/"
              className="flex items-center gap-1 px-2 py-1.5 rounded-lg text-[13px] font-medium text-[var(--text-body)] hover:bg-[var(--bg-panel)] hover:text-[var(--fortune-red)] transition-colors cursor-pointer"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M19 12H5M12 19l-7-7 7-7" />
              </svg>
              <span className="hidden sm:inline">{t("nav.home")}</span>
            </Link>
            <div className="w-9 h-9 rounded-xl bg-[rgba(215,92,112,0.10)] flex items-center justify-center">
              <Package size={20} weight="fill" className="text-[var(--fortune-red)]" />
            </div>
            <div>
              <h1 className="text-base font-semibold text-[var(--text-h1)]">{t("nav.brandAssets")}</h1>
              <p className="text-[12px] text-[var(--text-body)] mt-0.5">{t("brand.searchPlaceholder")}</p>
            </div>
          </div>
        </div>

        {/* Search + Source Filter */}
        <div className="flex gap-3 mb-6">
          <div className="relative flex-1">
            <MagnifyingGlass className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" size={16} weight="fill" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t("brand.searchPlaceholder")}
              className="apple-input text-sm pl-9 pr-4 w-full"
            />
          </div>
          <div className="flex gap-1">
            {(["all", "ai", "manual", "imported"] as const).map((src) => (
              <button
                key={src}
                onClick={() => setSourceFilter(src)}
                className={`px-3 py-2 rounded-lg text-xs font-medium transition-all cursor-pointer border ${
                  sourceFilter === src
                    ? "bg-[rgba(215,92,112,0.10)] border-[var(--fortune-red)] text-[var(--fortune-red)]"
                    : "bg-[var(--bg-card)] border-[rgba(215,92,112,0.18)] text-[var(--text-body)] hover:border-[var(--border-default)]"
                }`}
              >
                {src === "all" && t("brand.filter.all")}
                {src === "ai" && <><Sparkle size={12} weight="fill" className="inline mr-1" />{t("brand.filter.ai")}</>}
                {src === "manual" && <><UploadSimple size={12} weight="fill" className="inline mr-1" />{t("brand.filter.manual")}</>}
                {src === "imported" && <><Package size={12} weight="fill" className="inline mr-1" />{t("brand.filter.imported")}</>}
              </button>
            ))}
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="apple-card p-3 border-l-4 border-[var(--crimson-mist)] bg-[rgba(196,91,80,0.08)] flex items-center gap-2 mb-4">
            <WarningCircle size={16} weight="fill" className="text-[var(--crimson-mist)] shrink-0" />
            <span className="text-xs text-[var(--crimson-mist)] font-medium flex-1">{error}</span>
            <button onClick={() => setError(null)} className="text-[var(--crimson-mist)] hover:opacity-70 cursor-pointer">
              <X size={16} weight="fill" />
            </button>
          </div>
        )}

        {/* Main: Sidebar + Grid */}
        <div className="flex gap-6">
          {/* Left Sidebar */}
          <div className="w-52 shrink-0">
            <div className="sticky top-6 space-y-1">
              {CATEGORIES.map((cat) => {
                const Icon = cat.icon;
                const count = categoryCounts[cat.id] || 0;
                const isActive = activeCategory === cat.id;
                return (
                  <button
                    key={cat.id}
                    onClick={() => setActiveCategory(cat.id)}
                    className={`flex items-center gap-2.5 w-full px-3 py-2.5 rounded-xl text-xs font-medium transition-all cursor-pointer text-left ${
                      isActive
                        ? "bg-[rgba(215,92,112,0.10)] text-[var(--fortune-red)]"
                        : "text-[var(--text-body)] hover:bg-[var(--bg-panel)] hover:text-[var(--text-h1)]"
                    }`}
                  >
                    <Icon size={16} weight="fill" />
                    <span className="flex-1">{t(cat.labelKey)}</span>
                    <span className={`text-[12px] px-1.5 py-0.5 rounded-full ${
                      isActive ? "bg-[rgba(215,92,112,0.20)] text-[var(--fortune-red)]" : "bg-[var(--bg-panel)] text-[var(--text-muted)]"
                    }`}>
                      {count}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Right Content */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-[var(--text-h1)]">{t(activeLabel)}</h2>
              <span className="text-[12px] text-[var(--text-muted)]">
                {filteredAssets.length} {t("brand.assetCount")}
              </span>
            </div>

            {loading && (
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {Array.from({ length: 6 }).map((_, i) => (
                  <div key={i} className="apple-card overflow-hidden animate-pulse">
                    <div className="aspect-video bg-[var(--bg-panel)]" />
                    <div className="p-3 space-y-2">
                      <div className="h-3 bg-[var(--bg-panel)] rounded w-3/4" />
                      <div className="h-2 bg-[var(--bg-panel)] rounded w-1/2" />
                    </div>
                  </div>
                ))}
              </div>
            )}

            {!loading && filteredAssets.length === 0 && (
              <div className="apple-card p-12 text-center">
                <Package size={40} weight="fill" className="text-[rgba(215,92,112,0.18)] mx-auto mb-3" />
                <p className="text-sm font-medium text-[var(--text-body)]">{t("brand.empty")}</p>
                <p className="text-xs text-[var(--text-muted)] mt-1">{t("brand.emptyHint")}</p>
              </div>
            )}

            {!loading && filteredAssets.length > 0 && (
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {filteredAssets.map((asset) => (
                  <AssetCard key={asset.id} asset={asset} />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
