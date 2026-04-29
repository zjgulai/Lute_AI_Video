"use client";

import { useState, useEffect } from "react";
import { fetchAssets, getMediaUrl } from "./api";
import { useI18n } from "@/i18n/I18nProvider";

interface MediaItem {
  filename: string;
  path: string;
  size: number;
  type: "video" | "image" | "audio" | "document";
  created: string;
}

type FilterType = "all" | "video" | "image";

const PAGE_SIZE = 4;

export default function PortfolioGallery() {
  const { t } = useI18n();
  const [items, setItems] = useState<MediaItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<FilterType>("video");
  const [page, setPage] = useState(0);
  const [preview, setPreview] = useState<MediaItem | null>(null);

  useEffect(() => {
    fetchAssets()
      .then((files) => {
        const filtered = files.filter(
          (f: any) => (f.type === "video" || f.type === "image") && f.size >= 500 * 1024
        );
        // Sort by raw timestamp first, then map to display format
        filtered.sort((a: any, b: any) => b.created - a.created);
        const mapped: MediaItem[] = filtered.map((f: any) => ({
          filename: f.filename,
          path: f.path,
          size: f.size,
          type: f.type as MediaItem["type"],
          created: new Date(f.created * 1000).toLocaleDateString("zh-CN", {
            month: "short",
            day: "numeric",
          }),
        }));
        setItems(mapped);
      })
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);

  const filtered =
    filter === "all" ? items : items.filter((i) => i.type === filter);

  const paged = filtered.slice(0, (page + 1) * PAGE_SIZE);
  const hasMore = paged.length < filtered.length;

  const formatSize = (bytes: number) => {
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  };

  const getTitle = (filename: string) => {
    return filename
      .replace(/\.(mp4|png|jpg|jpeg|webp)$/i, "")
      .replace(/_/g, " ")
      .replace(/^seedance_/, "")
      .replace(/^poyo_img_test_/, "")
      .substring(0, 24);
  };

  if (loading) {
    return (
      <div className="pt-4 border-t border-[#e8e8ed]">
        <div className="flex items-center justify-between mb-3">
          <h4 className="text-[11px] font-semibold text-[#86868b] uppercase tracking-wider">
            {t("gallery.title")}
          </h4>
        </div>
        <div className="grid grid-cols-2 gap-2.5">
          {[1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="aspect-[4/3] rounded-2xl skeleton"
            />
          ))}
        </div>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="pt-4 border-t border-[#e8e8ed]">
        <h4 className="text-[11px] font-semibold text-[#86868b] uppercase tracking-wider mb-3">
          {t("gallery.title")}
        </h4>
        <div className="text-center py-8 rounded-2xl bg-[#fafafc] border border-dashed border-[#e8e8ed]">
          <div className="w-10 h-10 rounded-xl bg-[#f5f5f7] flex items-center justify-center mx-auto mb-2.5">
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="#d2d2d7"
              strokeWidth="1.5"
            >
              <rect x="3" y="3" width="18" height="18" rx="2" />
              <circle cx="8.5" cy="8.5" r="1.5" />
              <polyline points="21 15 16 10 5 21" />
            </svg>
          </div>
          <p className="text-[11px] text-[#aeaeb2] font-medium">{t("gallery.empty")}</p>
          <p className="text-[10px] text-[#d2d2d7] mt-0.5">
            {t("gallery.emptyHint")}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="pt-4 border-t border-[#e8e8ed]">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-[11px] font-semibold text-[#86868b] uppercase tracking-wider">
          {t("gallery.title")}
        </h4>
        <div className="flex gap-1">
          {(
            [
              { key: "all", label: t("gallery.all") },
              { key: "video", label: t("gallery.video") },
              { key: "image", label: t("gallery.image") },
            ] as { key: FilterType; label: string }[]
          ).map((f) => (
            <button
              key={f.key}
              onClick={() => {
                setFilter(f.key);
                setPage(0);
              }}
              className={`text-[10px] font-semibold px-2 py-0.5 rounded-full transition-all ${
                filter === f.key
                  ? "bg-[#7CB342] text-white"
                  : "bg-[#f5f5f7] text-[#aeaeb2] hover:bg-[#e8e8ed]"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-2 gap-2.5">
        {paged.map((item, i) => (
          <div
            key={i}
            onClick={() => setPreview(item)}
            className="group relative rounded-2xl overflow-hidden bg-[#f5f5f7] block shadow-sm hover:shadow-md transition-all duration-300 cursor-pointer"
            title={item.filename}
          >
            {/* Media */}
            <div className="aspect-[4/3] relative">
              {item.type === "image" ? (
                <img
                  src={getMediaUrl(item.path)}
                  alt={item.filename}
                  className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
                  onError={(e) => {
                    (e.target as HTMLImageElement).style.display = "none";
                  }}
                  loading="lazy"
                />
              ) : (
                <video
                  src={getMediaUrl(item.path)}
                  className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
                  preload="metadata"
                  muted
                />
              )}

              {/* Hover overlay */}
              <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-all duration-300 flex items-center justify-center">
                <div className="w-9 h-9 rounded-full bg-white/90 backdrop-blur-sm flex items-center justify-center opacity-0 group-hover:opacity-100 transform scale-75 group-hover:scale-100 transition-all duration-300 shadow-lg">
                  {item.type === "video" ? (
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="#1d1d1f">
                      <polygon points="8,5 19,12 8,19" />
                    </svg>
                  ) : (
                    <svg
                      width="14"
                      height="14"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="#1d1d1f"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                      <polyline points="7 10 12 15 17 10" />
                      <line x1="12" y1="15" x2="12" y2="3" />
                    </svg>
                  )}
                </div>
              </div>

              {/* Type badge */}
              <div
                className={`absolute top-2 right-2 px-1.5 py-0.5 rounded-md text-[9px] font-semibold backdrop-blur-md ${
                  item.type === "video"
                    ? "bg-black/50 text-white"
                    : "bg-white/80 text-[#1d1d1f]"
                }`}
              >
                {item.type === "video" ? t("gallery.video") : t("gallery.image")}
              </div>
            </div>

            {/* Info bar */}
            <div className="px-2.5 py-2 bg-white">
              <p className="text-[11px] font-medium text-[#1d1d1f] truncate leading-tight">
                {getTitle(item.filename)}
              </p>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className="text-[9px] text-[#aeaeb2]">
                  {formatSize(item.size)}
                </span>
                <span className="w-0.5 h-0.5 rounded-full bg-[#d2d2d7]" />
                <span className="text-[9px] text-[#aeaeb2]">{item.created}</span>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Load more */}
      {hasMore && (
        <button
          onClick={() => setPage((p) => p + 1)}
          className="w-full mt-3 py-2 rounded-xl bg-[#fafafc] border border-[#e8e8ed] text-[11px] font-medium text-[#86868b] hover:bg-[#f5f5f7] hover:text-[#1d1d1f] transition-all cursor-pointer"
        >
          {t("gallery.loadMore")} ({filtered.length - paged.length}{t("gallery.items")})
        </button>
      )}

      {/* Stats footer */}
      <p className="text-[10px] text-[#d2d2d7] text-center mt-2">
        {t("gallery.total")} {filtered.length}{t("gallery.items")}
        {filter !== "all" && ` · ${filter === "video" ? t("gallery.video") : t("gallery.image")}`}
      </p>

      {/* Preview Modal */}
      {preview && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm"
          onClick={() => setPreview(null)}
        >
          <div
            className="relative max-w-4xl max-h-[90vh] w-full mx-4 rounded-2xl overflow-hidden bg-black shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Close button */}
            <button
              onClick={() => setPreview(null)}
              className="absolute top-3 right-3 z-10 w-8 h-8 rounded-full bg-black/50 text-white flex items-center justify-center hover:bg-black/70 transition-colors cursor-pointer"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>

            {preview.type === "video" ? (
              <video
                src={getMediaUrl(preview.path)}
                controls
                autoPlay
                className="w-full max-h-[80vh] object-contain"
                onError={() => setPreview(null)}
              />
            ) : (
              <img
                src={getMediaUrl(preview.path)}
                alt={preview.filename}
                className="w-full max-h-[80vh] object-contain"
                onError={() => setPreview(null)}
              />
            )}

            {/* Filename */}
            <div className="absolute bottom-0 left-0 right-0 p-3 bg-gradient-to-t from-black/60 to-transparent">
              <p className="text-xs text-white font-medium">{preview.filename}</p>
              <p className="text-[10px] text-white/70">{formatSize(preview.size)} · {preview.created}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
