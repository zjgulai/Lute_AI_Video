"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useI18n } from "@/i18n/I18nProvider";
import { API_BASE, getMediaUrl as getApiMediaUrl } from "@/components/api";
import {
  Film,
  Upload,
  Image,
  Trash2,
  X,
  AlertCircle,
  Loader2,
  Tag,
  FileVideo,
  FileImage,
  Calendar,
  HardDrive,
  Edit3,
  Check,
  Search,
} from "lucide-react";

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

// Detect demo mode (same logic as api.ts)
const IS_DEMO_MODE =
  (typeof process !== "undefined" &&
    process.env.NEXT_PUBLIC_IS_DEMO === "true") ||
  (typeof window !== "undefined" &&
    (window.location.hostname.includes("github.io") ||
      window.location.hostname.endsWith(".vercel.app")));

function getMediaUrl(filename: string): string {
  if (!filename) return "";
  // Demo mode: serve from static public folder
  if (IS_DEMO_MODE) {
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

  const fetchAssets = useCallback(async () => {
    setLoading(true);
    setError(null);
    // Demo mode: load mock data
    if (IS_DEMO_MODE) {
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
    if (IS_DEMO_MODE) {
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
            <div className="w-9 h-9 rounded-xl bg-[#7CB342]/10 flex items-center justify-center">
              <Film className="w-5 h-5 text-[#7CB342]" />
            </div>
            <div>
              <h1 className="text-base font-semibold text-[#1d1d1f]">{t("footage.title")}</h1>
              <p className="text-[11px] text-[#86868b] mt-0.5">
                {t("footage.manageDesc")}
              </p>
            </div>
          </div>
          <button
            onClick={() => fileInputRef.current?.click()}
            className="apple-btn apple-btn-primary text-xs py-2 px-3"
          >
            <Upload className="w-3.5 h-3.5" />
            {t("footage.upload")}
          </button>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept="image/*,video/*"
            onChange={handleFileSelect}
            className="hidden"
          />
        </div>

        {/* Search bar */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#aeaeb2]" />
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
          <div className="apple-card p-3 border-l-4 border-[#ff453a] bg-[#fff5f5] flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-[#ff453a] shrink-0" />
            <span className="text-xs text-[#ff453a] font-medium flex-1">{error}</span>
            <button
              onClick={() => setError(null)}
              className="text-[#ff453a] hover:opacity-70 cursor-pointer"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {/* Upload progress banner */}
        {(uploading || uploadProgress) && (
          <div className="apple-card p-3 border-l-4 border-[#7CB342] bg-[#f7fbf0] flex items-center gap-2">
            <Loader2 className="w-4 h-4 text-[#7CB342] animate-spin shrink-0" />
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
              ? "border-[#7CB342] bg-[#7CB342]/5 scale-[1.01]"
              : "border-[#e8e8ed] hover:border-[#d2d2d7] hover:bg-[#fafafc]"
          }`}
        >
          <Upload className="w-8 h-8 text-[#aeaeb2] mx-auto mb-3" />
          <p className="text-sm text-[#86868b] font-medium">
            {t("footage.dragUpload")}
            <button
              onClick={() => fileInputRef.current?.click()}
              className="text-[#7CB342] hover:underline font-semibold mx-1 cursor-pointer"
            >
              {t("footage.clickSelect")}
            </button>
          </p>
          <p className="text-[11px] text-[#aeaeb2] mt-1">
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
                <Film className="w-10 h-10 text-[#e8e8ed] mx-auto mb-3" />
                <p className="text-sm font-medium text-[#86868b] mb-1">{t("footage.empty")}</p>
                <p className="text-xs text-[#aeaeb2] mb-4">
                  {t("footage.emptyHint")}
                </p>
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="apple-btn apple-btn-primary text-xs py-2 px-3"
                >
                  <Upload className="w-3.5 h-3.5" />
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
                          ? "ring-2 ring-[#7CB342] shadow-md"
                          : ""
                      }`}
                    >
                      {/* Thumbnail */}
                      <div className="aspect-video bg-[#1d1d1f] relative flex items-center justify-center overflow-hidden">
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
                        ) : null}
                        <div
                          className={`absolute inset-0 flex items-center justify-center ${
                            isImageType && mediaUrl ? "hidden" : ""
                          }`}
                        >
                          {isVideoType ? (
                            <FileVideo className="w-8 h-8 text-white/60" />
                          ) : (
                            <FileImage className="w-8 h-8 text-white/60" />
                          )}
                        </div>
                        {isVideoType && (
                          <div className="absolute bottom-1.5 right-1.5 px-1.5 py-0.5 rounded bg-black/60 text-[10px] text-white/80 font-medium">
                            {formatFileSize(asset.file_size)}
                          </div>
                        )}
                      </div>

                      {/* Info */}
                      <div className="p-2.5">
                        <p className="text-[11px] font-medium text-[#1d1d1f] truncate">
                          {asset.original_name}
                        </p>
                        <p className="text-[10px] text-[#aeaeb2] mt-0.5">
                          {formatFileSize(asset.file_size)}
                        </p>
                        {asset.tags.length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-1.5">
                            {asset.tags.slice(0, 3).map((tag, i) => (
                              <span
                                key={i}
                                className="px-1.5 py-0.5 rounded-full bg-[#7CB342]/10 text-[9px] text-[#7CB342] font-medium"
                              >
                                {tag}
                              </span>
                            ))}
                            {asset.tags.length > 3 && (
                              <span className="text-[9px] text-[#aeaeb2]">
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
                        className="absolute top-2 right-2 p-1.5 rounded-lg bg-black/40 text-white/70 hover:text-[#ff453a] hover:bg-black/60 opacity-0 group-hover:opacity-100 transition-all cursor-pointer"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
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
                  <h3 className="text-sm font-semibold text-[#1d1d1f]">{t("footage.detailTitle")}</h3>
                  <button
                    onClick={() => {
                      setSelectedAsset(null);
                      setEditingTags(false);
                    }}
                    className="p-1 rounded-lg text-[#aeaeb2] hover:text-[#1d1d1f] hover:bg-[#f5f5f7] transition-all cursor-pointer"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>

                {/* Preview */}
                <div className="aspect-video bg-[#1d1d1f] rounded-lg flex items-center justify-center overflow-hidden">
                  {isImage(selectedAsset.mime_type) ? (
                    <img
                      src={getMediaUrl(selectedAsset.filename)}
                      alt={selectedAsset.original_name}
                      className="w-full h-full object-contain"
                    />
                  ) : (
                    <FileVideo className="w-10 h-10 text-white/40" />
                  )}
                </div>

                {/* Metadata */}
                <div className="space-y-2">
                  <div className="flex items-start gap-2">
                    <HardDrive className="w-3.5 h-3.5 text-[#aeaeb2] mt-0.5 shrink-0" />
                    <div className="min-w-0">
                      <p className="text-[10px] text-[#aeaeb2]">{t("footage.filename")}</p>
                      <p className="text-[11px] text-[#1d1d1f] break-all">
                        {selectedAsset.original_name}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <HardDrive className="w-3.5 h-3.5 text-[#aeaeb2] shrink-0" />
                    <div>
                      <p className="text-[10px] text-[#aeaeb2]">{t("footage.fileSize")}</p>
                      <p className="text-[11px] text-[#1d1d1f]">
                        {formatFileSize(selectedAsset.file_size)}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Calendar className="w-3.5 h-3.5 text-[#aeaeb2] shrink-0" />
                    <div>
                      <p className="text-[10px] text-[#aeaeb2]">{t("footage.uploadTime")}</p>
                      <p className="text-[11px] text-[#1d1d1f]">
                        {formatDate(selectedAsset.metadata?.uploaded_at || selectedAsset.file_path)}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-start gap-2">
                    <Tag className="w-3.5 h-3.5 text-[#aeaeb2] mt-0.5 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between">
                        <p className="text-[10px] text-[#aeaeb2]">{t("footage.tags")}</p>
                        {!editingTags && (
                          <button
                            onClick={() => openTagEditor(selectedAsset)}
                            className="text-[10px] text-[#7CB342] hover:underline cursor-pointer"
                          >
                            <Edit3 className="w-3 h-3 inline mr-0.5" />
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
                          <p className="text-[9px] text-[#aeaeb2]">
                            {t("footage.tagHint")}
                          </p>
                          <div className="flex gap-1.5">
                            <button
                              onClick={saveTags}
                              className="apple-btn apple-btn-primary text-[10px] py-1 px-2"
                            >
                              <Check className="w-3 h-3" />
                              {t("footage.save")}
                            </button>
                            <button
                              onClick={() => setEditingTags(false)}
                              className="apple-btn text-[10px] py-1 px-2"
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
                                className="px-1.5 py-0.5 rounded-full bg-[#7CB342]/10 text-[10px] text-[#7CB342] font-medium"
                              >
                                {tag}
                              </span>
                            ))
                          ) : (
                            <span className="text-[10px] text-[#aeaeb2]">{t("footage.noTags")}</span>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                {/* Delete button */}
                <button
                  onClick={() => setDeleteConfirm(selectedAsset.asset_id)}
                  className="w-full apple-btn text-[11px] py-2 text-[#ff453a] hover:bg-[#ff453a]/5 border-[#ff453a]/20"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  {t("footage.deleteAsset")}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Delete confirmation dialog */}
      {deleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="apple-card p-5 max-w-sm mx-4">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-8 h-8 rounded-full bg-[#ff453a]/10 flex items-center justify-center">
                <AlertCircle className="w-4 h-4 text-[#ff453a]" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-[#1d1d1f]">{t("footage.deleteConfirm")}</h3>
                <p className="text-[11px] text-[#86868b]">
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
                    <Loader2 className="w-3 h-3 animate-spin" />
                    {t("footage.deleting")}
                  </span>
                ) : (
                  <span className="flex items-center gap-1.5">
                    <Trash2 className="w-3.5 h-3.5" />
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
