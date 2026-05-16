"use client";

import { useState, useEffect, useCallback } from "react";
import { getMediaUrl, apiFetch } from "./api";
import { useI18n } from "@/i18n/I18nProvider";

interface Asset {
  filename: string;
  path: string;
  size: number;
  type: "video" | "image" | "audio";
  created: string;
  tags: string[];
}

interface Props {
  onClose: () => void;
}

function collectTags(f: any): string[] {
  const out: string[] = [];
  if (typeof f.label === "string" && f.label.trim()) out.push(f.label.trim());
  if (Array.isArray(f.tags)) out.push(...f.tags.map((x: unknown) => String(x)).filter(Boolean));
  return [...new Set(out)].slice(0, 12);
}

export default function AssetLibrary({ onClose }: Props) {
  const { t, locale } = useI18n();
  const [assets, setAssets] = useState<Asset[]>([]);
  const [filter, setFilter] = useState<"all" | "video" | "image" | "audio">("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [preview, setPreview] = useState<Asset | null>(null);

  const loadAssets = useCallback(() => {
    setLoading(true);
    setError(false);
    apiFetch("/portfolio/")
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        const files = data.files || [];
        const mapped: Asset[] = files.map((f: any) => {
          const mime = f.mime_type || "";
          let type: Asset["type"] = "video";
          if (mime.startsWith("image/")) type = "image";
          else if (mime.startsWith("audio/")) type = "audio";
          return {
            filename: f.filename,
            path: f.path,
            size: f.size_bytes,
            type,
            created: f.produced_at
              ? new Date(f.produced_at).toLocaleString(locale === "zh" ? "zh-CN" : "en-US")
              : "-",
            tags: f.scenario ? [f.category, f.scenario] : [f.category],
          };
        });
        setAssets(mapped);
      })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [locale]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadAssets();
  }, [loadAssets]);

  const filtered = filter === "all" ? assets : assets.filter((a) => a.type === filter);

  const getIcon = (type: string) => {
    switch (type) {
      case "video": return "🎬";
      case "image": return "🖼️";
      case "audio": return "🎵";
      default: return "🎵";
    }
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  };

  const openNewTab = (asset: Asset) => {
    const url = getMediaUrl(asset.path);
    if (url) window.open(url, "_blank", "noopener,noreferrer");
  };

  return (
    <div className="apple-modal-overlay" onClick={onClose}>
      <div
        className="apple-card w-full max-w-3xl max-h-[80vh] flex flex-col animate-scale-in"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-[rgba(215,92,112,0.18)]">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-xl bg-[rgba(215,92,112,0.10)] flex items-center justify-center">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#D75C70" strokeWidth="2">
                <rect x="3" y="3" width="18" height="18" rx="2" />
                <circle cx="8.5" cy="8.5" r="1.5" />
                <polyline points="21 15 16 10 5 21" />
              </svg>
            </div>
            <h2 className="text-base font-semibold text-[var(--text-h1)]">{t("asset.title")}</h2>
          </div>
          <button type="button" onClick={onClose} className="w-8 h-8 rounded-lg hover:bg-[var(--bg-panel)] flex items-center justify-center cursor-pointer">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#D2C3BE" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Filters */}
        <div className="flex gap-1.5 p-3 border-b border-[rgba(215,92,112,0.18)] overflow-x-auto">
          {(["all", "video", "image", "audio"] as const).map((f) => (
            <button
              type="button"
              key={f}
              onClick={() => setFilter(f)}
              className={`apple-pill ${filter === f ? "active" : ""}`}
            >
              {f === "all" ? t("asset.all") : f === "video" ? t("asset.video") : f === "image" ? t("asset.image") : t("asset.audio")}
              {f === "all" && assets.length > 0 && (
                <span className="ml-1 text-[11px]">{assets.length}</span>
              )}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-4">
          {loading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-16 rounded-xl skeleton" />
              ))}
            </div>
          ) : error ? (
            <div className="text-center py-12">
              <div className="w-16 h-16 rounded-2xl bg-[rgba(140,60,75,0.10)] flex items-center justify-center mx-auto mb-3">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#8C3C4B" strokeWidth="1.5">
                  <circle cx="12" cy="12" r="10" />
                  <line x1="15" y1="9" x2="9" y2="15" />
                  <line x1="9" y1="9" x2="15" y2="15" />
                </svg>
              </div>
              <p className="text-sm text-[var(--text-body)]">{t("asset.loadFailed")}</p>
              <button type="button" onClick={loadAssets} className="apple-btn apple-btn-primary mt-3 text-xs py-1.5 px-4">
                {t("asset.retry")}
              </button>
            </div>
          ) : filtered.length === 0 ? (
            <div className="text-center py-12">
              <div className="w-16 h-16 rounded-2xl bg-[var(--bg-panel)] flex items-center justify-center mx-auto mb-3">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#A0918E" strokeWidth="1.5">
                  <rect x="3" y="3" width="18" height="18" rx="2" />
                  <circle cx="8.5" cy="8.5" r="1.5" />
                  <polyline points="21 15 16 10 5 21" />
                </svg>
              </div>
              <p className="text-sm text-[var(--text-body)]">{t("asset.empty")}</p>
              <p className="text-[11px] text-[var(--text-muted)] mt-1">{t("asset.emptyHint")}</p>
            </div>
          ) : (
            <div className="grid grid-cols-3 gap-3">
              {filtered.map((asset) => (
                <div
                  key={asset.path + asset.filename}
                  role="button"
                  tabIndex={0}
                  onClick={() => setPreview(asset)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      setPreview(asset);
                    }
                  }}
                  className="apple-card p-3 hover-lift cursor-pointer group block text-left"
                  title={t("asset.preview")}
                >
                  <div className="aspect-video bg-[var(--bg-panel)] rounded-lg flex items-center justify-center mb-2 overflow-hidden img-zoom relative">
                    {asset.type === "image" ? (
                      getMediaUrl(asset.path) ? (
                        <img
                          src={getMediaUrl(asset.path)}
                          alt={asset.filename}
                          className="w-full h-full object-cover pointer-events-none select-none"
                          draggable={false}
                          onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                        />
                      ) : (
                        <div className="flex flex-col items-center justify-center gap-1 text-center px-2">
                          <span className="text-2xl">🖼️</span>
                          <span className="text-[11px] text-[var(--text-muted)]">Demo</span>
                        </div>
                      )
                    ) : asset.type === "video" ? (
                      getMediaUrl(asset.path) ? (
                        <>
                          <video
                            src={getMediaUrl(asset.path)}
                            className="w-full h-full object-cover pointer-events-none select-none"
                            preload="metadata"
                            muted
                            playsInline
                          />
                          <div className="absolute inset-0 flex items-center justify-center bg-black/20 group-hover:bg-black/30 transition-colors pointer-events-none">
                            <div className="w-10 h-10 rounded-full bg-white/90 flex items-center justify-center shadow-lg">
                              <svg width="16" height="16" viewBox="0 0 24 24" fill="#1C1415">
                                <polygon points="8,5 19,12 8,19" />
                              </svg>
                            </div>
                          </div>
                        </>
                      ) : (
                        <div className="flex flex-col items-center justify-center gap-1 text-center px-2">
                          <span className="text-2xl">🎬</span>
                          <span className="text-[11px] text-[var(--text-muted)]">Demo</span>
                        </div>
                      )
                    ) : (
                      <span className="text-3xl">{getIcon(asset.type)}</span>
                    )}
                  </div>
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <p className="text-[11px] text-[var(--text-h1)] truncate">{asset.filename}</p>
                      <p className="text-[11px] text-[var(--text-muted)]">{formatSize(asset.size)} · {asset.created}</p>
                      {asset.tags.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-1.5">
                          {asset.tags.map((tag) => (
                            <span
                              key={tag}
                              className="inline-block max-w-[7rem] truncate text-[9px] font-medium px-1.5 py-0.5 rounded-full bg-[rgba(215,92,112,0.10)] text-[var(--fortune-red)]"
                              title={tag}
                            >
                              {tag}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#A0918E" strokeWidth="2" className="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity mt-0.5">
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                      <polyline points="7 10 12 15 17 10" />
                      <line x1="12" y1="15" x2="12" y2="3" />
                    </svg>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {preview && (
        <div
          className="fixed inset-0 z-[60] flex flex-col items-center justify-center bg-black/75 backdrop-blur-sm p-4"
          onClick={() => setPreview(null)}
          role="presentation"
        >
          <div
            className="relative w-full max-w-4xl max-h-[90vh] flex flex-col rounded-2xl overflow-hidden bg-[var(--bg-page)] shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between gap-2 px-3 py-2 border-b border-white/10">
              <p className="text-xs text-white/90 truncate font-medium pr-2" title={preview.filename}>
                {preview.filename}
              </p>
              <div className="flex items-center gap-2 shrink-0">
                <button
                  type="button"
                  className="text-[11px] px-2 py-1 rounded-lg bg-white/10 text-white hover:bg-white/20"
                  onClick={() => openNewTab(preview)}
                >
                  {t("asset.openInNewTab")}
                </button>
                <button
                  type="button"
                  className="w-8 h-8 rounded-lg bg-white/10 text-white flex items-center justify-center hover:bg-white/20"
                  onClick={() => setPreview(null)}
                  aria-label="Close"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <line x1="18" y1="6" x2="6" y2="18" />
                    <line x1="6" y1="6" x2="18" y2="18" />
                  </svg>
                </button>
              </div>
            </div>
            <div className="flex-1 min-h-0 flex items-center justify-center bg-black p-2">
              {preview.type === "video" && (
                <video
                  src={getMediaUrl(preview.path)}
                  className="max-h-[75vh] max-w-full object-contain"
                  controls
                  autoPlay
                  playsInline
                />
              )}
              {preview.type === "image" && (
                <img
                  src={getMediaUrl(preview.path)}
                  alt={preview.filename}
                  className="max-h-[75vh] max-w-full object-contain"
                />
              )}
              {preview.type === "audio" && (
                <div className="w-full max-w-md p-6 flex flex-col items-center gap-4">
                  <span className="text-4xl">{getIcon("audio")}</span>
                  <audio src={getMediaUrl(preview.path)} controls preload="metadata" className="w-full" />
                </div>
              )}
            </div>
            {preview.tags.length > 0 && (
              <div className="flex flex-wrap gap-1 px-3 py-2 border-t border-white/10 bg-black/40">
                {preview.tags.map((tag) => (
                  <span
                    key={tag}
                    className="text-[10px] px-2 py-0.5 rounded-full bg-white/15 text-white/90"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
