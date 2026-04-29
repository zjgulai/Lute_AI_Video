"use client";

import { useState, useEffect } from "react";
import { getMediaUrl, fetchAssets } from "./api";
import { useI18n } from "@/i18n/I18nProvider";

interface Asset {
  filename: string;
  path: string;
  size: number;
  type: "video" | "image" | "audio" | "document";
  created: string;
}

interface Props {
  onClose: () => void;
}

export default function AssetLibrary({ onClose }: Props) {
  const { t, locale } = useI18n();
  const [assets, setAssets] = useState<Asset[]>([]);
  const [filter, setFilter] = useState<"all" | "video" | "image" | "audio" | "document">("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const loadAssets = () => {
    setLoading(true);
    setError(false);
    fetchAssets()
      .then((files) => {
        const mapped: Asset[] = files.map((f: any) => ({
          filename: f.filename,
          path: f.path,
          size: f.size,
          type: f.type as Asset["type"],
          created: new Date(f.created * 1000).toLocaleString(locale === "zh" ? "zh-CN" : "en-US"),
        }));
        setAssets(mapped);
      })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadAssets();
  }, []);

  const filtered = filter === "all" ? assets : assets.filter((a) => a.type === filter);

  const getIcon = (type: string) => {
    switch (type) {
      case "video": return "🎬";
      case "image": return "🖼️";
      case "audio": return "🎵";
      default: return "📄";
    }
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  };

  return (
    <div className="apple-modal-overlay" onClick={onClose}>
      <div
        className="apple-card w-full max-w-3xl max-h-[80vh] flex flex-col animate-scale-in"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-[#e8e8ed]">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-xl bg-[#7CB342]/10 flex items-center justify-center">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#7CB342" strokeWidth="2">
                <rect x="3" y="3" width="18" height="18" rx="2" />
                <circle cx="8.5" cy="8.5" r="1.5" />
                <polyline points="21 15 16 10 5 21" />
              </svg>
            </div>
            <h2 className="text-base font-semibold text-[#1d1d1f]">{t("asset.title")}</h2>
          </div>
          <button onClick={onClose} className="w-8 h-8 rounded-lg hover:bg-[#f5f5f7] flex items-center justify-center cursor-pointer">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#86868b" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Filters */}
        <div className="flex gap-1.5 p-3 border-b border-[#e8e8ed] overflow-x-auto">
          {(["all", "video", "image", "audio", "document"] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`apple-pill ${filter === f ? "active" : ""}`}
            >
              {f === "all" ? t("asset.all") : f === "video" ? t("asset.video") : f === "image" ? t("asset.image") : f === "audio" ? t("asset.audio") : t("asset.document")}
              {f === "all" && assets.length > 0 && (
                <span className="ml-1 text-[10px]">{assets.length}</span>
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
              <div className="w-16 h-16 rounded-2xl bg-[#fff5f5] flex items-center justify-center mx-auto mb-3">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#ff453a" strokeWidth="1.5">
                  <circle cx="12" cy="12" r="10" />
                  <line x1="15" y1="9" x2="9" y2="15" />
                  <line x1="9" y1="9" x2="15" y2="15" />
                </svg>
              </div>
              <p className="text-sm text-[#86868b]">{t("asset.loadFailed")}</p>
              <button onClick={loadAssets} className="apple-btn apple-btn-primary mt-3 text-xs py-1.5 px-4">
                {t("asset.retry")}
              </button>
            </div>
          ) : filtered.length === 0 ? (
            <div className="text-center py-12">
              <div className="w-16 h-16 rounded-2xl bg-[#f5f5f7] flex items-center justify-center mx-auto mb-3">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#aeaeb2" strokeWidth="1.5">
                  <rect x="3" y="3" width="18" height="18" rx="2" />
                  <circle cx="8.5" cy="8.5" r="1.5" />
                  <polyline points="21 15 16 10 5 21" />
                </svg>
              </div>
              <p className="text-sm text-[#86868b]">{t("asset.empty")}</p>
              <p className="text-[11px] text-[#aeaeb2] mt-1">{t("asset.emptyHint")}</p>
            </div>
          ) : (
            <div className="grid grid-cols-3 gap-3">
              {filtered.map((asset, i) => (
                <a
                  key={i}
                  href={getMediaUrl(asset.path)}
                  target={asset.type === "video" ? "_blank" : undefined}
                  rel={asset.type === "video" ? "noopener noreferrer" : undefined}
                  download={asset.type !== "video" ? asset.filename : undefined}
                  className="apple-card p-3 hover-lift cursor-pointer group block no-underline"
                  title={asset.type === "video" ? t("result.view") : t("asset.download")}
                >
                  <div className="aspect-video bg-[#1d1d1f] rounded-lg flex items-center justify-center mb-2 overflow-hidden img-zoom relative">
                    {asset.type === "image" ? (
                      getMediaUrl(asset.path) ? (
                        <img
                          src={getMediaUrl(asset.path)}
                          alt={asset.filename}
                          className="w-full h-full object-cover"
                          onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                        />
                      ) : (
                        <div className="flex flex-col items-center justify-center gap-1 text-center px-2">
                          <span className="text-2xl">🖼️</span>
                          <span className="text-[9px] text-[#aeaeb2]">Demo</span>
                        </div>
                      )
                    ) : asset.type === "video" ? (
                      getMediaUrl(asset.path) ? (
                        <>
                          <video
                            src={getMediaUrl(asset.path)}
                            className="w-full h-full object-cover"
                            preload="metadata"
                            muted
                          />
                          {/* Play button overlay */}
                          <div className="absolute inset-0 flex items-center justify-center bg-black/20 group-hover:bg-black/30 transition-colors pointer-events-none">
                            <div className="w-10 h-10 rounded-full bg-white/90 flex items-center justify-center shadow-lg">
                              <svg width="16" height="16" viewBox="0 0 24 24" fill="#1d1d1f">
                                <polygon points="8,5 19,12 8,19" />
                              </svg>
                            </div>
                          </div>
                        </>
                      ) : (
                        <div className="flex flex-col items-center justify-center gap-1 text-center px-2">
                          <span className="text-2xl">🎬</span>
                          <span className="text-[9px] text-[#aeaeb2]">Demo</span>
                        </div>
                      )
                    ) : (
                      <span className="text-3xl">{getIcon(asset.type)}</span>
                    )}
                  </div>
                  <div className="flex items-center justify-between">
                    <div className="min-w-0">
                      <p className="text-[11px] text-[#1d1d1f] truncate">{asset.filename}</p>
                      <p className="text-[10px] text-[#aeaeb2]">{formatSize(asset.size)} · {asset.created}</p>
                    </div>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#aeaeb2" strokeWidth="2" className="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                      <polyline points="7 10 12 15 17 10" />
                      <line x1="12" y1="15" x2="12" y2="3" />
                    </svg>
                  </div>
                </a>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
