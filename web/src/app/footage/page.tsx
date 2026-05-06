"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import Link from "next/link";
import { useI18n } from "@/i18n/I18nProvider";
import { apiFetch, getMediaUrl, isDemoMode } from "@/components/api";
import {
  FilmStrip,
  UploadSimple,
  Image,
  Trash,
  X,
  WarningCircle,
  Spinner,
  Tag,
  Video,
  FileImage,
  Calendar,
  HardDrives,
  PencilSimple,
  Check,
  MagnifyingGlass,
  SquaresFour,
  FolderOpen,
} from "@phosphor-icons/react";
import GalleryGrid from "@/components/GalleryGrid";

interface FootageAsset {
  asset_id: string;
  filename: string;
  original_name: string;
  file_path: string;
  file_size: number;
  mime_type: string;
  thumbnail_path?: string;
  tags: string[];
  metadata: Record<string, any>;
}

function formatFileSize(bytes: number): string {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  const size = (bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0);
  return `${size} ${units[i]}`;
}

function formatDate(dateStr: string): string {
  if (!dateStr) return "-";
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return dateStr;
  }
}

function isVideo(mimeType: string): boolean {
  return mimeType.startsWith("video/");
}

function isImage(mimeType: string): boolean {
  return mimeType.startsWith("image/");
}

export default function FootagePage() {
  const { t } = useI18n();
  const [assets, setAssets] = useState<FootageAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Unified preview modal (replaces detail panel + window.open)
  const [previewAsset, setPreviewAsset] = useState<FootageAsset | null>(null);

  // Search / filter
  const [searchQuery, setSearchQuery] = useState("");

  // UI 2.0: Gallery tabs — finished works vs materials
  const [activeTab, setActiveTab] = useState<"finished" | "materials">("finished");

  // Materials category filter
  const [materialFilter, setMaterialFilter] = useState<"all" | "video" | "image" | "audio">("all");

  // Finished works: derived from assets (renders category video files)
  const finishedWorks = assets
    .filter((a) => isVideo(a.mime_type) && a.metadata?.category === "renders" && a.file_size > 1024 * 1024)
    .map((a) => ({
      id: a.asset_id,
      title: a.original_name,
      scene: a.metadata?.scenario || a.tags[1] || "other",
      videoType: "mp4",
      thumbnail: a.thumbnail_path || "",
      videoPath: a.file_path,
      duration: 0,
      createdAt: a.metadata?.produced_at || new Date().toISOString(),
    }));

  // Fetch portfolio files from /api/portfolio/ (pipeline-generated media)
  const fetchAssets = useCallback(async () => {
    setLoading(true);
    setError(null);
    // Demo mode: load mock data
    if (isDemoMode()) {
      try {
        const { DEMO_FOOTAGE_ASSETS } = await import("@/demo-data");
        setAssets(DEMO_FOOTAGE_ASSETS || []);
      } catch (e: any) {
        setError(e.message || t("common.fetchFailed"));
      } finally {
        setLoading(false);
      }
      return;
    }
    try {
      // TOP-50 quality sort: renders + fast_mode first, then by produced_at desc
      const res = await apiFetch("/portfolio/?limit=50&sort=quality");
      if (!res.ok) throw new Error(`${t("common.fetchFailed")} (${res.status})`);
      const data = await res.json();
      // Map PortfolioFile → FootageAsset shape so grid/detail panel render unchanged
      const mapped = (data.files || []).map((item: any) => ({
        asset_id: item.id,
        filename: item.filename,
        original_name: item.filename,
        file_path: item.path,
        file_size: item.size_bytes,
        mime_type: item.mime_type,
        thumbnail_path: item.thumbnail_path,
        tags: item.scenario ? [item.category, item.scenario] : [item.category],
        metadata: {
          category: item.category,
          scenario: item.scenario,
          label: item.label,
          produced_at: item.produced_at,
        },
      }));
      setAssets(mapped);
    } catch (e: any) {
      setError(e.message || t("common.fetchFailed"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAssets();
  }, [fetchAssets]);

  // ── Upload ──

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const files = Array.from(e.dataTransfer.files).filter((f) =>
      f.type.startsWith("video/") || f.type.startsWith("image/")
    );
    if (files.length > 0) {
      uploadFiles(files);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (files.length > 0) {
      uploadFiles(files);
    }
  };

  const uploadFiles = async (files: File[]) => {
    if (isDemoMode()) {
      setError("Demo mode — upload is not available");
      return;
    }
    setUploading(true);
    setError(null);
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      setUploadProgress(`${t("footage.uploading")} (${i + 1}${t("footage.of")}${files.length}): ${file.name}`);
      try {
        const formData = new FormData();
        formData.append("file", file);
        formData.append("tags", "footage");
        formData.append("metadata", JSON.stringify({ source: "footage-upload" }));

        const res = await apiFetch("/api/assets/upload", {
          method: "POST",
          body: formData,
        });
        if (!res.ok) throw new Error(`${t("footage.uploadFailed")} (${res.status})`);
      } catch (e: any) {
        setError(e.message || `${t("footage.uploadFailed")}: "${file.name}"`);
      }
    }
    setUploadProgress(null);
    setUploading(false);
    await fetchAssets();
  };

  // ── Preview helpers ──

  const openPreview = (asset: FootageAsset) => setPreviewAsset(asset);
  const closePreview = () => setPreviewAsset(null);

  // ── Filtering ──

  const filteredAssets = searchQuery.trim()
    ? assets.filter((a) => {
        const q = searchQuery.toLowerCase();
        return (
          a.original_name.toLowerCase().includes(q) ||
          a.filename.toLowerCase().includes(q) ||
          a.tags.some((t) => t.toLowerCase().includes(q))
        );
      })
    : assets;

  const materialFilteredAssets = filteredAssets.filter((a) => {
    if (materialFilter === "all") return true;
    if (materialFilter === "video") return isVideo(a.mime_type);
    if (materialFilter === "image") return isImage(a.mime_type);
    if (materialFilter === "audio") return a.mime_type.startsWith("audio/");
    return true;
  });

  // ── Render ──

  return (
    <div className="min-h-screen bg-[var(--color-bg)]">
      <div className="max-w-6xl mx-auto px-4 py-6 space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link href="/" className="flex items-center gap-1 px-2 py-1.5 rounded-lg text-[13px] font-medium text-[var(--text-body)] hover:bg-[var(--bg-panel)] hover:text-[var(--fortune-red)] transition-colors cursor-pointer">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
              <span className="hidden sm:inline">{t("nav.home")}</span>
            </Link>
            <div className="w-9 h-9 rounded-xl bg-[rgba(215,92,112,0.10)] flex items-center justify-center">
              <FilmStrip size={20} weight="fill" className="text-[var(--fortune-red)]" />
            </div>
            <div>
              <h1 className="text-base font-semibold text-[var(--text-h1)]">{t("gallery.title")}</h1>
              <p className="text-[12px] text-[var(--text-body)] mt-0.5">
                {t("gallery.groupByScene")}
              </p>
            </div>
          </div>
          {activeTab === "materials" && (
            <button
              onClick={() => fileInputRef.current?.click()}
              className="apple-btn apple-btn-primary text-xs py-2 px-3"
            >
              <UploadSimple size={16} weight="fill" />
              {t("footage.upload")}
            </button>
          )}
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept="image/*,video/*"
            onChange={handleFileSelect}
            className="hidden"
          />
        </div>

        {/* Tab Navigation */}
        <div className="flex gap-1 border-b border-[rgba(215,92,112,0.18)] pb-0"
        >
          <button
            onClick={() => setActiveTab("finished")}
            className={`flex items-center gap-1.5 px-4 py-2.5 text-xs font-medium transition-all border-b-2 cursor-pointer ${
              activeTab === "finished"
                ? "border-[var(--fortune-red)] text-[var(--fortune-red)]"
                : "border-transparent text-[var(--text-body)] hover:text-[var(--text-h1)]"
            }`}
          >
            <SquaresFour size={16} weight="fill" />
            {t("gallery.tab.finished")}
          </button>
          <button
            onClick={() => setActiveTab("materials")}
            className={`flex items-center gap-1.5 px-4 py-2.5 text-xs font-medium transition-all border-b-2 cursor-pointer ${
              activeTab === "materials"
                ? "border-[var(--fortune-red)] text-[var(--fortune-red)]"
                : "border-transparent text-[var(--text-body)] hover:text-[var(--text-h1)]"
            }`}
          >
            <FolderOpen size={16} weight="fill" />
            {t("gallery.tab.materials")}
          </button>
        </div>

        {/* ── Finished Works Tab ── */}
        {activeTab === "finished" && (
          <div className="animate-fade-in">
            <GalleryGrid
              items={finishedWorks}
              onPlay={(item) => {
                const asset = assets.find((a) => a.asset_id === item.id);
                if (asset) openPreview(asset);
              }}
            />
          </div>
        )}

        {/* ── Materials Tab ── */}
        {activeTab === "materials" && (
          <div className="space-y-4 animate-fade-in">
            {/* Search bar + category filter */}
            <div className="flex gap-3 items-center">
              <div className="relative flex-1">
                <MagnifyingGlass className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" size={16} weight="fill" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder={t("footage.searchPlaceholder")}
                  className="apple-input text-sm pl-9 pr-4 w-full"
                />
              </div>
              <div className="flex gap-1 shrink-0">
                {(["all", "video", "image", "audio"] as const).map((f) => (
                  <button
                    key={f}
                    onClick={() => setMaterialFilter(f)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer ${
                      materialFilter === f
                        ? "bg-[rgba(215,92,112,0.12)] text-[var(--fortune-red)]"
                        : "text-[var(--text-body)] hover:bg-[var(--bg-panel)]"
                    }`}
                  >
                    {f === "all" && "全部"}
                    {f === "video" && "视频"}
                    {f === "image" && "图片"}
                    {f === "audio" && "音频"}
                  </button>
                ))}
              </div>
            </div>

        {/* Error banner */}
        {error && (
          <div className="apple-card p-3 border-l-4 border-[var(--crimson-mist)] bg-[rgba(196,91,80,0.08)] flex items-center gap-2">
            <WarningCircle size={16} weight="fill" className="text-[var(--crimson-mist)] shrink-0" />
            <span className="text-xs text-[var(--crimson-mist)] font-medium flex-1">{error}</span>
            <button
              onClick={() => setError(null)}
              className="text-[var(--crimson-mist)] hover:opacity-70 cursor-pointer"
            >
              <X size={16} weight="fill" />
            </button>
          </div>
        )}

        {/* Upload progress banner */}
        {(uploading || uploadProgress) && (
          <div className="apple-card p-3 border-l-4 border-[var(--fortune-red)] bg-[var(--bg-panel)] flex items-center gap-2">
            <Spinner size={16} weight="fill" className="text-[var(--fortune-red)] animate-spin shrink-0" />
            <span className="text-xs text-[var(--jade-accent)] font-medium">
              {uploadProgress || t("footage.uploadProgress")}
            </span>
          </div>
        )}

        {/* Drag-drop upload zone */}
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className={`border-2 border-dashed rounded-xl p-8 text-center transition-all ${
            dragOver
              ? "border-[var(--fortune-red)] bg-[rgba(215,92,112,0.05)] scale-[1.01]"
              : "border-[rgba(215,92,112,0.18)] hover:border-[var(--border-default)] hover:bg-[rgba(215,92,112,0.05)]"
          }`}
        >
          <UploadSimple size={32} weight="fill" className="text-[var(--text-muted)] mx-auto mb-3" />
          <p className="text-sm text-[var(--text-body)] font-medium">
            {t("footage.dragUpload")}
            <button
              onClick={() => fileInputRef.current?.click()}
              className="text-[var(--fortune-red)] hover:underline font-semibold mx-1 cursor-pointer"
            >
              {t("footage.clickSelect")}
            </button>
          </p>
          <p className="text-[12px] text-[var(--text-muted)] mt-1">
            {t("footage.supportedFormats")}
          </p>
        </div>

        {/* Content area: Gallery */}
        <div className="min-h-[300px]">
            {/* Loading skeleton */}
            {loading && (
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
                {Array.from({ length: 8 }).map((_, i) => (
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

            {/* Empty state */}
            {!loading && materialFilteredAssets.length === 0 && (
              <div className="apple-card p-12 text-center">
                <FilmStrip size={40} weight="fill" className="text-[rgba(215,92,112,0.18)] mx-auto mb-3" />
                <p className="text-sm font-medium text-[var(--text-body)] mb-1">{t("footage.empty")}</p>
                <p className="text-xs text-[var(--text-muted)] mb-4">
                  {t("footage.emptyHint")}
                </p>
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="apple-btn apple-btn-primary text-xs py-2 px-3"
                >
                  <UploadSimple size={16} weight="fill" />
                  {t("footage.selectFiles")}
                </button>
              </div>
            )}

            {/* Asset grid — frontend filter: video/image > 1 MiB, audio any size */}
            {!loading && materialFilteredAssets.length > 0 && (
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
                {materialFilteredAssets
                  .filter((a) => {
                    const min = 1024 * 1024;
                    if (isVideo(a.mime_type) || isImage(a.mime_type)) return a.file_size > min;
                    return true;
                  })
                  .map((asset) => {
                  const mediaUrl = getMediaUrl(asset.file_path);
                  const isVideoType = isVideo(asset.mime_type);
                  const isImageType = isImage(asset.mime_type);

                  return (
                    <div
                      key={asset.asset_id}
                      onClick={() => openPreview(asset)}
                      className="apple-card overflow-hidden cursor-pointer transition-all duration-200 hover:shadow-md group"
                    >
                      {/* Thumbnail */}
                      <div className="aspect-video bg-[var(--cinema-black)] relative flex items-center justify-center overflow-hidden">
                        {isImageType && mediaUrl ? (
                          <img
                            src={mediaUrl}
                            alt={asset.original_name}
                            className="w-full h-full object-cover"
                            loading="lazy"
                            onError={(e) => {
                              (e.target as HTMLImageElement).style.display = "none";
                              (e.target as HTMLImageElement).nextElementSibling?.classList.remove("hidden");
                            }}
                          />
                        ) : isVideoType && mediaUrl ? (
                          <>
                            {asset.thumbnail_path ? (
                              <img
                                src={getMediaUrl(asset.thumbnail_path)}
                                alt={asset.original_name}
                                className="w-full h-full object-cover"
                                loading="lazy"
                              />
                            ) : (
                              <div className="w-full h-full bg-[var(--bg-panel)] flex items-center justify-center">
                                <Video size={32} weight="fill" className="text-[var(--text-muted)]" />
                              </div>
                            )}
                            <div className="absolute inset-0 flex items-center justify-center bg-black/0 group-hover:bg-black/20 transition-all">
                              <div className="w-8 h-8 rounded-full bg-white/90 flex items-center justify-center shadow-md opacity-0 group-hover:opacity-100 transition-all scale-90 group-hover:scale-100">
                                <svg width="12" height="12" viewBox="0 0 24 24" style={{ fill: "var(--text-h1)" }}>
                                  <polygon points="8,5 19,12 8,19" />
                                </svg>
                              </div>
                            </div>
                          </>
                        ) : (
                          <div className="w-full h-full bg-[var(--bg-panel)] flex items-center justify-center">
                            {isVideoType ? (
                              <Video size={32} weight="fill" className="text-[var(--text-muted)]" />
                            ) : (
                              <FileImage size={32} weight="fill" className="text-[var(--text-muted)]" />
                            )}
                          </div>
                        )}
                        {isVideoType && (
                          <div className="absolute bottom-1.5 right-1.5 px-1.5 py-0.5 rounded bg-black/60 text-[12px] text-white/80 font-medium">
                            {formatFileSize(asset.file_size)}
                          </div>
                        )}
                      </div>

                      {/* Info */}
                      <div className="p-2.5">
                        <p className="text-[12px] font-medium text-[var(--text-h1)] truncate">
                          {asset.original_name}
                        </p>
                        <p className="text-[12px] text-[var(--text-muted)] mt-0.5">
                          {formatFileSize(asset.file_size)}
                        </p>
                        {asset.tags.length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-1.5">
                            {asset.tags.slice(0, 3).map((tag, i) => (
                              <span
                                key={i}
                                className="px-1.5 py-0.5 rounded-full bg-[rgba(215,92,112,0.10)] text-[12px] text-[var(--fortune-red)] font-medium"
                              >
                                {tag}
                              </span>
                            ))}
                            {asset.tags.length > 3 && (
                              <span className="text-[12px] text-[var(--text-muted)]">
                                +{asset.tags.length - 3}
                              </span>
                            )}
                          </div>
                        )}
                      </div>

                      {/* Note: delete disabled for portfolio view (files are read-only pipeline outputs) */}
                    </div>
                  );
                })}
              </div>
            )}
        </div>
      </div>
    )}

      {/* ── Unified Media Preview Modal ── */}
      {previewAsset && (
        <div
          className="fixed inset-0 z-[200] flex items-center justify-center bg-black/85 backdrop-blur-sm"
          onClick={closePreview}
        >
          <div
            className="relative max-w-[90vw] max-h-[90vh] flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Close button */}
            <button
              onClick={closePreview}
              className="absolute -top-10 right-0 p-2 rounded-full bg-white/10 text-white/80 hover:bg-white/20 hover:text-white transition-all cursor-pointer z-10"
            >
              <X size={20} weight="fill" />
            </button>

            {/* Media */}
            <div className="rounded-xl overflow-hidden bg-black/60">
              {isVideo(previewAsset.mime_type) ? (
                <video
                  src={getMediaUrl(previewAsset.file_path)}
                  controls
                  autoPlay
                  className="max-w-[85vw] max-h-[75vh] object-contain"
                  preload="metadata"
                />
              ) : isImage(previewAsset.mime_type) ? (
                <img
                  src={getMediaUrl(previewAsset.file_path)}
                  alt={previewAsset.original_name}
                  className="max-w-[85vw] max-h-[75vh] object-contain"
                />
              ) : (
                <div className="px-12 py-16 text-center">
                  <FileImage size={48} weight="fill" className="text-white/40 mx-auto mb-4" />
                  <audio
                    src={getMediaUrl(previewAsset.file_path)}
                    controls
                    className="w-64"
                  />
                </div>
              )}
            </div>

            {/* Info bar */}
            <div className="mt-3 px-4 py-3 rounded-xl bg-white/5 backdrop-blur">
              <div className="flex items-center gap-4 flex-wrap">
                <p className="text-sm text-white/90 font-medium">{previewAsset.original_name}</p>
                <span className="text-xs text-white/50">{formatFileSize(previewAsset.file_size)}</span>
                <span className="text-xs text-white/50">{previewAsset.mime_type}</span>
                {previewAsset.tags.length > 0 && (
                  <div className="flex gap-1">
                    {previewAsset.tags.map((tag, i) => (
                      <span
                        key={i}
                        className="px-2 py-0.5 rounded-full bg-[rgba(215,92,112,0.20)] text-[11px] text-[var(--misty-pink)] font-medium"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

    </div>
    </div>
  );
}
