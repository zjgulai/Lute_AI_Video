"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  MagnifyingGlass,
  UploadSimple,
  Spinner,
  WarningCircle,
  X,
  Video,
  FileImage,
  MusicNotes,
} from "@phosphor-icons/react";
import { useI18n } from "@/i18n/I18nProvider";
import { apiFetch, getMediaUrl, isDemoMode } from "@/components/api";
import EmptyState from "@/components/EmptyState";

interface MaterialAsset {
  id: string;
  filename: string;
  originalName: string;
  filePath: string;
  sizeBytes: number;
  mimeType: string;
  thumbnailPath: string | null;
  tags: string[];
  producedAt: string;
  isAiGenerated: boolean;
}

type TypeFilter = "all" | "video" | "image" | "audio";
const TYPE_FILTER_IDS: TypeFilter[] = ["all", "video", "image", "audio"];

function isVideoMime(m: string) { return m.startsWith("video/"); }
function isImageMime(m: string) { return m.startsWith("image/"); }
function isAudioMime(m: string) { return m.startsWith("audio/"); }

function formatSize(bytes: number): string {
  if (!bytes) return "";
  if (bytes >= 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(0)} MB`;
  return `${(bytes / 1024).toFixed(0)} KB`;
}

export default function MaterialsTab() {
  const { t } = useI18n();
  const [assets, setAssets] = useState<MaterialAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<TypeFilter>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<string | null>(null);
  const [preview, setPreview] = useState<MaterialAsset | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchAssets = useCallback(async () => {
    setLoading(true);
    setError(null);

    if (isDemoMode()) {
      try {
        const { DEMO_FOOTAGE_ASSETS } = await import("@/demo-data");
        const mapped: MaterialAsset[] = (DEMO_FOOTAGE_ASSETS || []).map((a: any, i: number) => ({
          id: a.asset_id || `demo-${i}`,
          filename: a.filename,
          originalName: a.original_name || a.filename,
          filePath: a.file_path,
          sizeBytes: a.file_size || 0,
          mimeType: a.mime_type || "application/octet-stream",
          thumbnailPath: a.thumbnail_path || null,
          tags: a.tags || [],
          producedAt: a.metadata?.uploaded_at || new Date().toISOString(),
          isAiGenerated: (a.tags || []).some((tg: string) => tg.includes("ai-") || tg.includes("seedance")),
        }));
        setAssets(mapped.filter((m) => !isVideoMime(m.mimeType) || m.sizeBytes === 0 || m.tags.every((t) => t !== "renders")));
      } catch (e: any) {
        setError(e.message || t("common.fetchFailed"));
      } finally {
        setLoading(false);
      }
      return;
    }

    try {
      const res = await apiFetch("/portfolio/?kind=creation_intermediate&limit=200&sort=recent");
      if (!res.ok) {
        const fallback = await apiFetch("/portfolio/?limit=200&sort=recent");
        if (!fallback.ok) throw new Error(`${t("common.fetchFailed")} (${fallback.status})`);
        const data = await fallback.json();
        const mapped: MaterialAsset[] = (data.files || [])
          .filter((f: any) => f.category !== "renders" && f.category !== "fast_mode")
          .map((f: any) => ({
            id: f.id,
            filename: f.filename,
            originalName: f.filename,
            filePath: f.path,
            sizeBytes: f.size_bytes,
            mimeType: f.mime_type,
            thumbnailPath: f.thumbnail_path,
            tags: [f.category],
            producedAt: f.produced_at,
            isAiGenerated: ["seedance", "gpt_images", "audio", "keyframes", "character_identity", "thumbnails"].includes(f.category),
          }));
        setAssets(mapped);
        return;
      }
      const data = await res.json();
      const mapped: MaterialAsset[] = (data.files || []).map((f: any) => ({
        id: f.id,
        filename: f.filename,
        originalName: f.filename,
        filePath: f.path,
        sizeBytes: f.size_bytes,
        mimeType: f.mime_type,
        thumbnailPath: f.thumbnail_path,
        tags: [f.category],
        producedAt: f.produced_at,
        isAiGenerated: ["seedance", "gpt_images", "audio", "keyframes", "character_identity", "thumbnails"].includes(f.category),
      }));
      setAssets(mapped);
    } catch (e: any) {
      setError(e.message || t("common.fetchFailed"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => { fetchAssets(); }, [fetchAssets]);

  const filteredAssets = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return assets.filter((a) => {
      if (typeFilter === "video" && !isVideoMime(a.mimeType)) return false;
      if (typeFilter === "image" && !isImageMime(a.mimeType)) return false;
      if (typeFilter === "audio" && !isAudioMime(a.mimeType)) return false;
      if (!q) return true;
      return (
        a.originalName.toLowerCase().includes(q) ||
        a.filename.toLowerCase().includes(q) ||
        a.tags.some((tag) => tag.toLowerCase().includes(q))
      );
    });
  }, [assets, typeFilter, searchQuery]);

  const uploadFiles = async (files: File[]) => {
    if (isDemoMode()) {
      setError("Demo 模式下无法上传");
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
        formData.append("tags", "materials,user_upload");
        formData.append("metadata", JSON.stringify({ source: "library-materials" }));
        const res = await apiFetch("/api/upload", { method: "POST", body: formData });
        if (!res.ok) throw new Error(`${t("footage.uploadFailed")} (${res.status})`);
      } catch (e: any) {
        setError(e.message || `${t("footage.uploadFailed")}: "${file.name}"`);
      }
    }
    setUploadProgress(null);
    setUploading(false);
    await fetchAssets();
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (files.length > 0) uploadFiles(files);
    e.target.value = "";
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <div className="flex gap-1">
          {TYPE_FILTER_IDS.map((id) => {
            const isActive = typeFilter === id;
            return (
              <button
                key={id}
                onClick={() => setTypeFilter(id)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer ${
                  isActive
                    ? "bg-[rgba(215,92,112,0.12)] text-[var(--fortune-red)]"
                    : "text-[var(--text-body)] hover:bg-[var(--bg-panel)]"
                }`}
              >
                {id === "all" && t("gallery.all")}
                {id === "video" && t("gallery.video")}
                {id === "image" && t("gallery.image")}
                {id === "audio" && t("gallery.audio")}
              </button>
            );
          })}
        </div>
        <div className="relative flex-1">
          <MagnifyingGlass className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" size={14} weight="fill" />
          <input
            id="materials-search"
            name="q"
            type="search"
            aria-label={t("library.tab.materials")}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={t("footage.searchPlaceholder")}
            className="apple-input text-sm pl-9 pr-4 w-full"
          />
        </div>
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading}
          className="apple-btn apple-btn-primary text-xs py-2 px-3 shrink-0 disabled:opacity-60"
        >
          <UploadSimple size={14} weight="fill" />
          {t("footage.upload")}
        </button>
        <input
          ref={fileInputRef}
          id="materials-file"
          name="file"
          type="file"
          multiple
          accept="image/*,video/*,audio/*"
          onChange={handleFileSelect}
          className="hidden"
          aria-label={t("footage.selectFiles")}
        />
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

      {(uploading || uploadProgress) && (
        <div className="apple-card p-3 border-l-4 border-[var(--fortune-red)] bg-[var(--bg-panel)] flex items-center gap-2">
          <Spinner size={16} weight="fill" className="text-[var(--fortune-red)] animate-spin shrink-0" />
          <span className="text-xs text-[var(--jade-accent)] font-medium">{uploadProgress || t("footage.uploadProgress")}</span>
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

      {!loading && filteredAssets.length === 0 && (
        (searchQuery || typeFilter !== "all") ? (
          <EmptyState
            illustration="search-empty"
            title={t("materials.noMatch", "没有匹配的素材")}
            description={t("works.tryDifferent", "换个关键词或筛选条件试试")}
          />
        ) : (
          <EmptyState
            illustration="materials"
            title={t("footage.empty")}
            description={t("footage.emptyHint")}
            action={
              <button
                data-empty-cta
                onClick={() => fileInputRef.current?.click()}
                className="apple-btn apple-btn-primary text-xs py-2 px-3"
              >
                <UploadSimple size={14} weight="fill" />
                {t("footage.selectFiles")}
              </button>
            }
          />
        )
      )}

      {!loading && filteredAssets.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
          {filteredAssets.map((asset) => {
            const url = getMediaUrl(asset.filePath);
            const thumb = asset.thumbnailPath ? getMediaUrl(asset.thumbnailPath) : "";
            const isVideo = isVideoMime(asset.mimeType);
            const isImage = isImageMime(asset.mimeType);
            const isAudio = isAudioMime(asset.mimeType);
            return (
              <button
                key={asset.id}
                data-asset-card
                data-kind="creation_intermediate"
                onClick={() => setPreview(asset)}
                className="apple-card overflow-hidden cursor-pointer transition-all duration-200 hover:shadow-md group text-left"
              >
                <div className="aspect-video bg-[var(--cinema-black)] relative flex items-center justify-center overflow-hidden">
                  {isImage && url ? (
                    <img src={url} alt={asset.originalName} className="w-full h-full object-cover" loading="lazy" />
                  ) : isVideo ? (
                    thumb ? (
                      <img src={thumb} alt={asset.originalName} className="w-full h-full object-cover" loading="lazy" />
                    ) : (
                      <div className="w-full h-full bg-[var(--bg-panel)] flex items-center justify-center">
                        <Video size={28} weight="fill" className="text-[var(--text-muted)]" />
                      </div>
                    )
                  ) : isAudio ? (
                    <div className="w-full h-full bg-[var(--bg-panel)] flex items-center justify-center">
                      <MusicNotes size={28} weight="fill" className="text-[var(--gold-foil)]" />
                    </div>
                  ) : (
                    <div className="w-full h-full bg-[var(--bg-panel)] flex items-center justify-center">
                      <FileImage size={28} weight="fill" className="text-[var(--text-muted)]" />
                    </div>
                  )}
                </div>
                <div className="p-4">
                  <p className="text-[12px] font-medium text-[var(--text-h1)] truncate">{asset.originalName}</p>
                  <div className="flex items-center gap-2 mt-1.5">
                    {asset.isAiGenerated && (
                      <span className="text-[11px] px-1.5 py-0.5 rounded-full bg-[rgba(215,92,112,0.10)] text-[var(--fortune-red)] font-medium">
                        {t("brand.filter.ai")}
                      </span>
                    )}
                    {!asset.isAiGenerated && asset.tags.length > 0 && (
                      <span className="text-[11px] px-1.5 py-0.5 rounded-full bg-[var(--bg-panel)] text-[var(--text-muted)] font-medium">
                        {asset.tags[0]}
                      </span>
                    )}
                    <span className="text-[11px] text-[var(--text-muted)] ml-auto">{formatSize(asset.sizeBytes)}</span>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      )}

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
              {isVideoMime(preview.mimeType) ? (
                <video src={getMediaUrl(preview.filePath)} controls autoPlay className="max-w-[85vw] max-h-[75vh] object-contain" />
              ) : isImageMime(preview.mimeType) ? (
                <img src={getMediaUrl(preview.filePath)} alt={preview.originalName} className="max-w-[85vw] max-h-[75vh] object-contain" />
              ) : (
                <div className="px-12 py-16 text-center">
                  <MusicNotes size={48} weight="fill" className="text-white/40 mx-auto mb-4" />
                  <audio src={getMediaUrl(preview.filePath)} controls className="w-64" />
                </div>
              )}
            </div>
            <div className="mt-3 px-4 py-3 rounded-xl bg-white/5 backdrop-blur">
              <p className="text-sm text-white/90 font-medium">{preview.originalName}</p>
              <p className="text-[11px] text-white/50 mt-1">{preview.mimeType} · {formatSize(preview.sizeBytes)}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
