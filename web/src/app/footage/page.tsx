"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import Link from "next/link";
import { useI18n } from "@/i18n/I18nProvider";
import { API_BASE, getMediaUrl as getApiMediaUrl, isDemoMode } from "@/components/api";
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

function getMediaUrl(filename: string): string {
  if (!filename) return "";
  // Demo mode: serve from static public folder
  if (isDemoMode()) {
    return getApiMediaUrl(filename);
  }
  // Assets stored via api_assets.py use the filename as the media path
  return API_BASE + "/api/media/" + encodeURIComponent(filename);
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

  // Detail panel
  const [selectedAsset, setSelectedAsset] = useState<FootageAsset | null>(null);

  // Tag editing
  const [editingTags, setEditingTags] = useState(false);
  const [tagInput, setTagInput] = useState("");

  // Delete confirmation
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  // Search / filter
  const [searchQuery, setSearchQuery] = useState("");

  // UI 2.0: Gallery tabs — finished works vs materials
  const [activeTab, setActiveTab] = useState<"finished" | "materials">("finished");

  // Gallery items (loaded from localStorage for demo)
  const [galleryItems, setGalleryItems] = useState<any[]>([]);

  useEffect(() => {
    try {
      const stored = localStorage.getItem("hermes_gallery_items");
      if (stored) {
        setGalleryItems(JSON.parse(stored));
      }
    } catch {
      // ignore parse errors
    }
  }, []);

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
      const res = await fetch(API_BASE + "/api/assets/", {
        headers: { "X-API-Key": "ai_video_demo_2026" },
      });
      if (!res.ok) throw new Error(`${t("common.fetchFailed")} (${res.status})`);
      const data = await res.json();
      setAssets(data.assets || []);
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

        const res = await fetch(API_BASE + "/api/assets/upload", {
          method: "POST",
          headers: { "X-API-Key": "ai_video_demo_2026" },
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

  // ── Tag editing ──

  const openTagEditor = (asset: FootageAsset) => {
    setSelectedAsset(asset);
    setTagInput(asset.tags.join(", "));
    setEditingTags(true);
  };

  const saveTags = async () => {
    if (!selectedAsset) return;
    const newTags = tagInput
      .split(",")
      .map((t) => t.trim())
      .filter((t) => t.length > 0);

    try {
      const res = await fetch(
        API_BASE + "/api/assets/" + selectedAsset.asset_id + "/tags",
        {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            "X-API-Key": "ai_video_demo_2026",
          },
          body: JSON.stringify({ tags: newTags }),
        }
      );
      if (!res.ok) throw new Error(`${t("common.updateFailed")} (${res.status})`);

      // Optimistically update local state
      setAssets((prev) =>
        prev.map((a) =>
          a.asset_id === selectedAsset.asset_id ? { ...a, tags: newTags } : a
        )
      );
      setSelectedAsset((prev) =>
        prev ? { ...prev, tags: newTags } : null
      );
      setEditingTags(false);
    } catch (e: any) {
      setError(e.message || t("common.updateFailed"));
    }
  };

  // ── Delete ──

  const handleDelete = async (assetId: string) => {
    setDeleting(true);
    try {
      const res = await fetch(API_BASE + "/api/assets/" + assetId, {
        method: "DELETE",
        headers: { "X-API-Key": "ai_video_demo_2026" },
      });
      if (!res.ok) throw new Error(`${t("common.deleteFailed")} (${res.status})`);
      setDeleteConfirm(null);
      if (selectedAsset?.asset_id === assetId) {
        setSelectedAsset(null);
      }
      await fetchAssets();
    } catch (e: any) {
      setError(e.message || t("common.deleteFailed"));
    } finally {
      setDeleting(false);
    }
  };

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

  // ── Render ──

  return (
    <div className="min-h-screen bg-[var(--color-bg)]">
      <div className="max-w-6xl mx-auto px-4 py-6 space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link href="/" className="flex items-center gap-1 px-2 py-1.5 rounded-lg text-[13px] font-medium text-[#59585E] hover:bg-[#FCE4E2] hover:text-[#6A2B3A] transition-colors cursor-pointer">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
              <span className="hidden sm:inline">{t("nav.home")}</span>
            </Link>
            <div className="w-9 h-9 rounded-xl bg-[#6A2B3A]/10 flex items-center justify-center">
              <FilmStrip size={20} weight="fill" className="text-[#6A2B3A]" />
            </div>
            <div>
              <h1 className="text-base font-semibold text-[#35353B]">{t("gallery.title")}</h1>
              <p className="text-[11px] text-[#59585E] mt-0.5">
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
        <div className="flex gap-1 border-b border-[#EDD3D1] pb-0"
        >
          <button
            onClick={() => setActiveTab("finished")}
            className={`flex items-center gap-1.5 px-4 py-2.5 text-xs font-medium transition-all border-b-2 cursor-pointer ${
              activeTab === "finished"
                ? "border-[#6A2B3A] text-[#6A2B3A]"
                : "border-transparent text-[#59585E] hover:text-[#35353B]"
            }`}
          >
            <SquaresFour size={16} weight="fill" />
            {t("gallery.tab.finished")}
          </button>
          <button
            onClick={() => setActiveTab("materials")}
            className={`flex items-center gap-1.5 px-4 py-2.5 text-xs font-medium transition-all border-b-2 cursor-pointer ${
              activeTab === "materials"
                ? "border-[#6A2B3A] text-[#6A2B3A]"
                : "border-transparent text-[#59585E] hover:text-[#35353B]"
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
              items={galleryItems}
              onPlay={(item) => {
                // Open video in new tab or modal
                if (item.videoPath) {
                  window.open(getMediaUrl(item.videoPath), "_blank");
                }
              }}
            />
          </div>
        )}

        {/* ── Materials Tab ── */}
        {activeTab === "materials" && (
          <div className="space-y-4 animate-fade-in">
            {/* Search bar */}
            <div className="relative">
              <MagnifyingGlass className="absolute left-3 top-1/2 -translate-y-1/2 text-[#9FA0A0]" size={16} weight="fill" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder={t("footage.searchPlaceholder")}
                className="apple-input text-sm pl-9 pr-4 w-full"
              />
            </div>

        {/* Error banner */}
        {error && (
          <div className="apple-card p-3 border-l-4 border-[#C45B50] bg-[#fff5f5] flex items-center gap-2">
            <WarningCircle size={16} weight="fill" className="text-[#C45B50] shrink-0" />
            <span className="text-xs text-[#C45B50] font-medium flex-1">{error}</span>
            <button
              onClick={() => setError(null)}
              className="text-[#C45B50] hover:opacity-70 cursor-pointer"
            >
              <X size={16} weight="fill" />
            </button>
          </div>
        )}

        {/* Upload progress banner */}
        {(uploading || uploadProgress) && (
          <div className="apple-card p-3 border-l-4 border-[#6A2B3A] bg-[#FCE4E2] flex items-center gap-2">
            <Spinner size={16} weight="fill" className="text-[#6A2B3A] animate-spin shrink-0" />
            <span className="text-xs text-[#558b2f] font-medium">
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
              ? "border-[#6A2B3A] bg-[#6A2B3A]/5 scale-[1.01]"
              : "border-[#EDD3D1] hover:border-[#D9A8A3] hover:bg-[#FFF5F2]"
          }`}
        >
          <UploadSimple size={32} weight="fill" className="text-[#9FA0A0] mx-auto mb-3" />
          <p className="text-sm text-[#59585E] font-medium">
            {t("footage.dragUpload")}
            <button
              onClick={() => fileInputRef.current?.click()}
              className="text-[#6A2B3A] hover:underline font-semibold mx-1 cursor-pointer"
            >
              {t("footage.clickSelect")}
            </button>
          </p>
          <p className="text-[11px] text-[#9FA0A0] mt-1">
            {t("footage.supportedFormats")}
          </p>
        </div>

        {/* Content area: Gallery + Detail panel */}
        <div className="flex gap-4">
          {/* Gallery */}
          <div className="flex-1 min-h-[300px]">
            {/* Loading skeleton */}
            {loading && (
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
                {Array.from({ length: 8 }).map((_, i) => (
                  <div key={i} className="apple-card overflow-hidden animate-pulse">
                    <div className="aspect-video bg-[#f0f0f5]" />
                    <div className="p-3 space-y-2">
                      <div className="h-3 bg-[#f0f0f5] rounded w-3/4" />
                      <div className="h-2 bg-[#f0f0f5] rounded w-1/2" />
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Empty state */}
            {!loading && filteredAssets.length === 0 && (
              <div className="apple-card p-12 text-center">
                <FilmStrip size={40} weight="fill" className="text-[#EDD3D1] mx-auto mb-3" />
                <p className="text-sm font-medium text-[#59585E] mb-1">{t("footage.empty")}</p>
                <p className="text-xs text-[#9FA0A0] mb-4">
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

            {/* Asset grid */}
            {!loading && filteredAssets.length > 0 && (
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
                {filteredAssets.map((asset) => {
                  const mediaUrl = getMediaUrl(asset.filename);
                  const isVideoType = isVideo(asset.mime_type);
                  const isImageType = isImage(asset.mime_type);
                  const isSelected = selectedAsset?.asset_id === asset.asset_id;

                  return (
                    <div
                      key={asset.asset_id}
                      onClick={() => {
                        setSelectedAsset(asset);
                        setEditingTags(false);
                      }}
                      className={`apple-card overflow-hidden cursor-pointer transition-all duration-200 hover:shadow-md group ${
                        isSelected
                          ? "ring-2 ring-[#6A2B3A] shadow-md"
                          : ""
                      }`}
                    >
                      {/* Thumbnail */}
                      <div className="aspect-video bg-[#35353B] relative flex items-center justify-center overflow-hidden">
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
                            <video
                              src={mediaUrl}
                              className="w-full h-full object-cover"
                              preload="metadata"
                              muted
                            />
                            <div className="absolute inset-0 flex items-center justify-center bg-black/20 pointer-events-none">
                              <div className="w-8 h-8 rounded-full bg-white/90 flex items-center justify-center shadow-md">
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="#35353B">
                                  <polygon points="8,5 19,12 8,19" />
                                </svg>
                              </div>
                            </div>
                          </>
                        ) : null}
                        <div
                          className={`absolute inset-0 flex items-center justify-center ${
                            (isImageType || isVideoType) && mediaUrl ? "hidden" : ""
                          }`}
                        >
                          {isVideoType ? (
                            <Video size={32} weight="fill" className="text-white/60" />
                          ) : (
                            <FileImage size={32} weight="fill" className="text-white/60" />
                          )}
                        </div>
                        {isVideoType && (
                          <div className="absolute bottom-1.5 right-1.5 px-1.5 py-0.5 rounded bg-black/60 text-[11px] text-white/80 font-medium">
                            {formatFileSize(asset.file_size)}
                          </div>
                        )}
                      </div>

                      {/* Info */}
                      <div className="p-2.5">
                        <p className="text-[11px] font-medium text-[#35353B] truncate">
                          {asset.original_name}
                        </p>
                        <p className="text-[11px] text-[#9FA0A0] mt-0.5">
                          {formatFileSize(asset.file_size)}
                        </p>
                        {asset.tags.length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-1.5">
                            {asset.tags.slice(0, 3).map((tag, i) => (
                              <span
                                key={i}
                                className="px-1.5 py-0.5 rounded-full bg-[#6A2B3A]/10 text-[11px] text-[#6A2B3A] font-medium"
                              >
                                {tag}
                              </span>
                            ))}
                            {asset.tags.length > 3 && (
                              <span className="text-[11px] text-[#9FA0A0]">
                                +{asset.tags.length - 3}
                              </span>
                            )}
                          </div>
                        )}
                      </div>

                      {/* Quick delete button */}
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setDeleteConfirm(asset.asset_id);
                        }}
                        className="absolute top-2 right-2 p-1.5 rounded-lg bg-black/40 text-white/70 hover:text-[#C45B50] hover:bg-black/60 opacity-0 group-hover:opacity-100 transition-all cursor-pointer"
                      >
                        <Trash size={16} weight="fill" />
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Detail panel */}
          {selectedAsset && (
            <div className="w-72 shrink-0">
              <div className="apple-card p-4 sticky top-6 space-y-3">
                <div className="flex items-start justify-between">
                  <h3 className="text-sm font-semibold text-[#35353B]">{t("footage.detailTitle")}</h3>
                  <button
                    onClick={() => {
                      setSelectedAsset(null);
                      setEditingTags(false);
                    }}
                    className="p-1 rounded-lg text-[#9FA0A0] hover:text-[#35353B] hover:bg-[#FCE4E2] transition-all cursor-pointer"
                  >
                    <X size={16} weight="fill" />
                  </button>
                </div>

                {/* Preview */}
                <div className="aspect-video bg-[#35353B] rounded-lg flex items-center justify-center overflow-hidden">
                  {isImage(selectedAsset.mime_type) ? (
                    <img
                      src={getMediaUrl(selectedAsset.filename)}
                      alt={selectedAsset.original_name}
                      className="w-full h-full object-contain"
                    />
                  ) : isVideo(selectedAsset.mime_type) ? (
                    <video
                      src={getMediaUrl(selectedAsset.filename)}
                      controls
                      className="w-full h-full object-contain"
                      preload="metadata"
                    />
                  ) : (
                    <Video size={40} weight="fill" className="text-white/40" />
                  )}
                </div>

                {/* Metadata */}
                <div className="space-y-2">
                  <div className="flex items-start gap-2">
                    <HardDrives size={16} weight="fill" className="text-[#9FA0A0] mt-0.5 shrink-0" />
                    <div className="min-w-0">
                      <p className="text-[11px] text-[#9FA0A0]">{t("footage.filename")}</p>
                      <p className="text-[11px] text-[#35353B] break-all">
                        {selectedAsset.original_name}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <HardDrives size={16} weight="fill" className="text-[#9FA0A0] shrink-0" />
                    <div>
                      <p className="text-[11px] text-[#9FA0A0]">{t("footage.fileSize")}</p>
                      <p className="text-[11px] text-[#35353B]">
                        {formatFileSize(selectedAsset.file_size)}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Calendar size={16} weight="fill" className="text-[#9FA0A0] shrink-0" />
                    <div>
                      <p className="text-[11px] text-[#9FA0A0]">{t("footage.uploadTime")}</p>
                      <p className="text-[11px] text-[#35353B]">
                        {formatDate(selectedAsset.metadata?.uploaded_at || selectedAsset.file_path)}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-start gap-2">
                    <Tag size={16} weight="fill" className="text-[#9FA0A0] mt-0.5 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between">
                        <p className="text-[11px] text-[#9FA0A0]">{t("footage.tags")}</p>
                        {!editingTags && (
                          <button
                            onClick={() => openTagEditor(selectedAsset)}
                            className="text-[11px] text-[#6A2B3A] hover:underline cursor-pointer"
                          >
                            <PencilSimple size={12} weight="fill" className="inline mr-0.5" />
                            {t("footage.editTags")}
                          </button>
                        )}
                      </div>
                      {editingTags ? (
                        <div className="mt-1 space-y-1.5">
                          <input
                            type="text"
                            value={tagInput}
                            onChange={(e) => setTagInput(e.target.value)}
                            placeholder={t("footage.tagPlaceholder")}
                            className="apple-input text-[11px] w-full"
                            autoFocus
                            onKeyDown={(e) => {
                              if (e.key === "Enter") saveTags();
                              if (e.key === "Escape") setEditingTags(false);
                            }}
                          />
                          <p className="text-[11px] text-[#9FA0A0]">
                            {t("footage.tagHint")}
                          </p>
                          <div className="flex gap-1.5">
                            <button
                              onClick={saveTags}
                              className="apple-btn apple-btn-primary text-[11px] py-1 px-2"
                            >
                              <Check size={12} weight="fill" />
                              {t("footage.save")}
                            </button>
                            <button
                              onClick={() => setEditingTags(false)}
                              className="apple-btn text-[11px] py-1 px-2"
                            >
                              {t("common.cancel")}
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div className="flex flex-wrap gap-1 mt-1">
                          {selectedAsset.tags.length > 0 ? (
                            selectedAsset.tags.map((tag, i) => (
                              <span
                                key={i}
                                className="px-1.5 py-0.5 rounded-full bg-[#6A2B3A]/10 text-[11px] text-[#6A2B3A] font-medium"
                              >
                                {tag}
                              </span>
                            ))
                          ) : (
                            <span className="text-[11px] text-[#9FA0A0]">{t("footage.noTags")}</span>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                {/* Delete button */}
                <button
                  onClick={() => setDeleteConfirm(selectedAsset.asset_id)}
                  className="w-full apple-btn text-[11px] py-2 text-[#C45B50] hover:bg-[#C45B50]/5 border-[#C45B50]/20"
                >
                  <Trash size={16} weight="fill" />
                  {t("footage.deleteAsset")}
                </button>
              </div>
            </div>
          )}
        </div>
          </div>
        )}
      </div>

      {/* Delete confirmation dialog */}
      {deleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="apple-card p-5 max-w-sm mx-4">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-8 h-8 rounded-full bg-[#C45B50]/10 flex items-center justify-center">
                <WarningCircle size={16} weight="fill" className="text-[#C45B50]" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-[#35353B]">{t("footage.deleteConfirm")}</h3>
                <p className="text-[11px] text-[#59585E]">
                  {t("footage.deleteHint")}
                </p>
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setDeleteConfirm(null)}
                className="apple-btn text-xs py-2 px-3"
                disabled={deleting}
              >
                {t("common.cancel")}
              </button>
              <button
                onClick={() => handleDelete(deleteConfirm)}
                disabled={deleting}
                className="apple-btn apple-btn-danger text-xs py-2 px-3"
              >
                {deleting ? (
                  <span className="flex items-center gap-1.5">
                    <Spinner size={12} weight="fill" className="animate-spin" />
                    {t("footage.deleting")}
                  </span>
                ) : (
                  <span className="flex items-center gap-1.5">
                    <Trash size={16} weight="fill" />
                    {t("common.delete")}
                  </span>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
