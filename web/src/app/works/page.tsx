"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { FilmSlate, MagnifyingGlass, WarningCircle, X } from "@phosphor-icons/react";
import { useI18n } from "@/i18n/I18nProvider";
import { apiFetch, getMediaUrl, isDemoMode } from "@/components/api";
import TopHeader from "@/components/TopHeader";
import EmptyState from "@/components/EmptyState";
import { ListSkeleton } from "@/components/Skeleton";
import Pagination from "@/components/Pagination";

import { errorMessage } from "@/lib/errors";
interface FinalWork {
  id: string;
  filename: string;
  path: string;
  scenario: string | null;
  label: string | null;
  producedAt: string;
  sizeBytes: number;
  mimeType: string;
  thumbnailPath: string | null;
}

const SCENE_FILTER_IDS = ["all", "product_direct", "brand_campaign", "influencer_remix", "brand_vlog"] as const;
type SceneFilter = typeof SCENE_FILTER_IDS[number];

const SCENE_ID_BY_PREFIX: Record<string, SceneFilter> = {
  s1: "product_direct",
  s2: "brand_campaign",
  s3: "influencer_remix",
  s5: "brand_vlog",
};

function inferSceneFilter(work: FinalWork): SceneFilter | "other" {
  if (work.scenario && work.scenario in SCENE_ID_BY_PREFIX) {
    return SCENE_ID_BY_PREFIX[work.scenario];
  }
  const stem = work.filename.toLowerCase();
  if (stem.startsWith("vlog")) return "brand_vlog";
  for (const [prefix, scene] of Object.entries(SCENE_ID_BY_PREFIX)) {
    if (stem.startsWith(prefix + "_") || stem.startsWith(prefix + ".")) return scene;
  }
  return "other";
}

function formatDate(iso: string, locale: string): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString(locale === "zh" ? "zh-CN" : "en-US", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    });
  } catch {
    return iso;
  }
}

function formatSize(bytes: number): string {
  if (!bytes) return "";
  if (bytes >= 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(0)} MB`;
  return `${(bytes / 1024).toFixed(0)} KB`;
}

function humanizeFilename(name: string): string {
  const stem = name.replace(/\.[^.]+$/, "");
  const m = /^(seedance|cosyvoice|poyo_img|gpt_image)_(.+)/i.exec(stem);
  if (m) {
    const tool = m[1].charAt(0).toUpperCase() + m[1].slice(1).toLowerCase();
    const rest = m[2].replace(/_/g, " ");
    return `${tool} · ${rest}`;
  }
  return stem.replace(/_/g, " ");
}

export default function WorksPage() {
  const { t, locale } = useI18n();
  const [works, setWorks] = useState<FinalWork[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sceneFilter, setSceneFilter] = useState<SceneFilter>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [preview, setPreview] = useState<FinalWork | null>(null);
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 24;

  const fetchWorks = useCallback(async () => {
    setLoading(true);
    setError(null);

    if (isDemoMode()) {
      try {
        const { DEMO_FOOTAGE_ASSETS } = await import("@/demo-data");
        const demoFinals: FinalWork[] = (DEMO_FOOTAGE_ASSETS || [])
          .filter((a: any) => a.mime_type?.startsWith("video/"))
          .map((a: any, i: number) => ({
            id: `demo-${i}`,
            filename: a.original_name || a.filename || `demo_${i}.mp4`,
            path: a.file_path,
            scenario: a.metadata?.scenario || null,
            label: a.metadata?.label || null,
            producedAt: a.metadata?.produced_at || a.metadata?.uploaded_at || new Date().toISOString(),
            sizeBytes: a.file_size || 0,
            mimeType: a.mime_type || "video/mp4",
            thumbnailPath: a.thumbnail_path || null,
          }));
        setWorks(demoFinals);
      } catch (e: unknown) {
        setError(errorMessage(e, t("common.fetchFailed")));
      } finally {
        setLoading(false);
      }
      return;
    }

    try {
      const res = await apiFetch("/portfolio/?kind=final_work&limit=500&sort=size_desc");
      if (!res.ok) {
        const res2 = await apiFetch("/portfolio/?limit=500&sort=size_desc");
        if (!res2.ok) throw new Error(`${t("common.fetchFailed")} (${res2.status})`);
        const data = await res2.json();
        const mapped: FinalWork[] = (data.files || [])
          .filter((f: any) => f.category === "renders" || f.category === "fast_mode")
          .map((f: any) => ({
            id: f.id,
            filename: f.filename,
            path: f.path,
            scenario: f.scenario,
            label: f.label,
            producedAt: f.produced_at,
            sizeBytes: f.size_bytes,
            mimeType: f.mime_type,
            thumbnailPath: f.thumbnail_path,
          }));
        setWorks(mapped);
        return;
      }
      const data = await res.json();
      const mapped: FinalWork[] = (data.files || []).map((f: any) => ({
        id: f.id,
        filename: f.filename,
        path: f.path,
        scenario: f.scenario,
        label: f.label,
        producedAt: f.produced_at,
        sizeBytes: f.size_bytes,
        mimeType: f.mime_type,
        thumbnailPath: f.thumbnail_path,
      }));
      setWorks(mapped);
    } catch (e: unknown) {
      setError(errorMessage(e, t("common.fetchFailed")));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    fetchWorks();
  }, [fetchWorks]);

  const enrichedWorks = useMemo(
    () => works.map((w) => ({ work: w, scene: inferSceneFilter(w) })),
    [works],
  );

  const sceneCounts = useMemo(() => {
    const counts: Record<SceneFilter, number> = {
      all: enrichedWorks.length,
      product_direct: 0,
      brand_campaign: 0,
      influencer_remix: 0,
      brand_vlog: 0,
    };
    for (const { scene } of enrichedWorks) {
      if (scene in counts) counts[scene as SceneFilter]++;
    }
    return counts;
  }, [enrichedWorks]);

  const filteredWorks = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return enrichedWorks.filter(({ work, scene }) => {
      if (sceneFilter !== "all" && scene !== sceneFilter) return false;
      if (!q) return true;
      return (
        work.filename.toLowerCase().includes(q) ||
        (work.label || "").toLowerCase().includes(q) ||
        (work.scenario || "").toLowerCase().includes(q)
      );
    });
  }, [enrichedWorks, sceneFilter, searchQuery]);

  const totalPages = Math.max(1, Math.ceil(filteredWorks.length / PAGE_SIZE));
  const safePage = Math.min(Math.max(1, page), totalPages);
  const pagedWorks = useMemo(() => {
    const start = (safePage - 1) * PAGE_SIZE;
    return filteredWorks.slice(start, start + PAGE_SIZE);
  }, [filteredWorks, safePage]);

  const handleFilterChange = (next: SceneFilter) => {
    setSceneFilter(next);
    setPage(1);
  };
  const handleSearchChange = (q: string) => {
    setSearchQuery(q);
    setPage(1);
  };

  return (
    <div className="min-h-screen bg-[var(--color-bg)] overflow-x-hidden">
      <TopHeader />
      <div className="max-w-6xl mx-auto px-4 py-6 space-y-5">
        <header className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-[rgba(215,92,112,0.10)] flex items-center justify-center">
            <FilmSlate size={20} weight="fill" className="text-[var(--fortune-red)]" />
          </div>
          <div>
            <h1 className="text-base font-semibold text-[var(--text-h1)]">{t("works.title")}</h1>
            <p className="text-[12px] text-[var(--text-body)] mt-0.5">{t("works.subtitle")}</p>
          </div>
        </header>

        <div className="flex flex-col sm:flex-row sm:items-center gap-3">
          <div className="flex gap-1 overflow-x-auto scrollbar-none">
            {SCENE_FILTER_IDS.map((id) => {
              const isActive = sceneFilter === id;
              const label = id === "all" ? t("works.filterAll") : t(`scene.${id}.title`);
              const count = sceneCounts[id] || 0;
              return (
                <button
                  key={id}
                  onClick={() => handleFilterChange(id)}
                  className={`shrink-0 px-3 py-1.5 rounded-full text-xs font-medium transition-all cursor-pointer border ${
                    isActive
                      ? "bg-[rgba(215,92,112,0.10)] border-[var(--fortune-red)] text-[var(--fortune-red)]"
                      : "bg-[var(--bg-card)] border-[rgba(215,92,112,0.18)] text-[var(--text-body)] hover:border-[var(--border-default)]"
                  }`}
                >
                  {label}
                  {count > 0 && (
                    <span className={`ml-1.5 text-[11px] ${isActive ? "opacity-70" : "text-[var(--text-muted)]"}`}>
                      {count}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
          <div className="relative flex-1">
            <MagnifyingGlass className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" size={14} weight="fill" />
            <input
              id="works-search"
              name="q"
              type="search"
              aria-label={t("works.title")}
              value={searchQuery}
              onChange={(e) => handleSearchChange(e.target.value)}
              placeholder={t("footage.searchPlaceholder")}
              className="apple-input text-sm pl-9 pr-4 w-full"
            />
          </div>
        </div>

        {error && (
          <div className="apple-card p-3 border-l-4 border-[var(--crimson-mist)] bg-[rgba(196,91,80,0.08)] flex items-center gap-2">
            <WarningCircle size={16} weight="fill" className="text-[var(--crimson-mist)] shrink-0" />
            <span className="text-xs text-[var(--crimson-mist)] font-medium flex-1">{error}</span>
            <button onClick={() => setError(null)} className="text-[var(--crimson-mist)] hover:opacity-70 cursor-pointer">
              <X size={16} weight="fill" />
            </button>
          </div>
        )}

        {loading && (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="apple-card overflow-hidden">
                <div className="aspect-video skeleton" />
                <div className="p-4 space-y-2">
                  <div className="h-3 skeleton w-3/4" />
                  <div className="h-2 skeleton w-1/2" />
                </div>
              </div>
            ))}
          </div>
        )}

        {!loading && filteredWorks.length === 0 && (
          (searchQuery || sceneFilter !== "all") ? (
            <EmptyState
              illustration="search-empty"
              title={t("works.noMatch", "没有匹配的作品")}
              description={t("works.tryDifferent", "换个关键词或筛选条件试试")}
            />
          ) : (
            <EmptyState
              illustration="works"
              title={t("works.empty")}
              description={t("works.emptyHint")}
              action={
                <Link
                  data-empty-cta
                  href="/"
                  className="apple-btn apple-btn-primary text-xs py-2 px-3 inline-flex"
                >
                  {t("nav.home")} →
                </Link>
              }
            />
          )
        )}

        {!loading && filteredWorks.length > 0 && (
          <>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
            {pagedWorks.map(({ work, scene }) => {
              const sceneLabel =
                scene === "other" ? "" : t(`scene.${scene}.title`);
              const thumbUrl = work.thumbnailPath ? getMediaUrl(work.thumbnailPath) : "";
              const title = work.label || humanizeFilename(work.filename);
              return (
                <button
                  key={work.id}
                  data-asset-card
                  data-kind="final_work"
                  onClick={() => setPreview(work)}
                  className="apple-card overflow-hidden cursor-pointer transition-all duration-200 hover:shadow-md group text-left"
                >
                  <div className="aspect-video bg-[var(--cinema-black)] relative flex items-center justify-center overflow-hidden">
                    {thumbUrl ? (
                      <img
                        src={thumbUrl}
                        alt={title}
                        className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
                        loading="lazy"
                      />
                    ) : (
                      <div className="w-full h-full bg-[var(--bg-panel)] flex items-center justify-center">
                        <FilmSlate size={28} weight="fill" className="text-[var(--text-muted)]" />
                      </div>
                    )}
                    <div className="absolute inset-0 flex items-center justify-center bg-black/0 group-hover:bg-black/20 transition-all">
                      <div className="w-10 h-10 rounded-full bg-white/90 flex items-center justify-center shadow-md opacity-0 group-hover:opacity-100 transition-all scale-90 group-hover:scale-100">
                        <svg width="14" height="14" viewBox="0 0 24 24" style={{ fill: "var(--text-h1)" }}>
                          <polygon points="8,5 19,12 8,19" />
                        </svg>
                      </div>
                    </div>
                  </div>
                  <div className="p-4">
                    <h3 className="text-[13px] font-medium text-[var(--text-h1)] truncate">{title}</h3>
                    <div className="flex items-center gap-2 mt-1.5">
                      {sceneLabel && (
                        <span className="text-[11px] px-1.5 py-0.5 rounded-full bg-[rgba(215,92,112,0.10)] text-[var(--fortune-red)] font-medium">
                          {sceneLabel}
                        </span>
                      )}
                      <span className="text-[11px] text-[var(--text-muted)]">
                        {formatDate(work.producedAt, locale)}
                      </span>
                      {work.sizeBytes > 0 && (
                        <span className="text-[11px] text-[var(--text-muted)] ml-auto">
                          {formatSize(work.sizeBytes)}
                        </span>
                      )}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
          <Pagination
            page={safePage}
            pageSize={PAGE_SIZE}
            total={filteredWorks.length}
            onPageChange={setPage}
          />
          </>
        )}
      </div>

      {preview && (
        <div
          className="fixed inset-0 z-[200] flex items-center justify-center bg-black/85 backdrop-blur-sm"
          onClick={() => setPreview(null)}
        >
          <div className="relative max-w-[90vw] max-h-[90vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
            <button
              onClick={() => setPreview(null)}
              className="absolute -top-10 right-0 p-2 rounded-full bg-white/10 text-white/80 hover:bg-white/20 hover:text-white transition-all cursor-pointer z-10"
              aria-label="Close"
            >
              <X size={20} weight="fill" />
            </button>
            <div className="rounded-xl overflow-hidden bg-black/60">
              <video
                src={getMediaUrl(preview.path)}
                poster={preview.thumbnailPath ? getMediaUrl(preview.thumbnailPath) : undefined}
                controls
                autoPlay
                muted
                playsInline
                className="max-w-[85vw] max-h-[75vh] object-contain"
                preload="metadata"
              />
            </div>
            <div className="mt-3 px-4 py-3 rounded-xl bg-white/5 backdrop-blur">
              <div className="flex items-center gap-4 flex-wrap">
                <p className="text-sm text-white/90 font-medium">
                  {preview.label || humanizeFilename(preview.filename)}
                </p>
                <span className="text-[11px] text-white/50">{formatSize(preview.sizeBytes)}</span>
                <span className="text-[11px] text-white/50">{formatDate(preview.producedAt, locale)}</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
