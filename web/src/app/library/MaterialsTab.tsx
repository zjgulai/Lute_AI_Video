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
import { errorMessage } from "@/lib/errors";
import EmptyState from "@/components/EmptyState";
import Pagination from "@/components/Pagination";
import RuntimeMediaImage from "@/components/RuntimeMediaImage";
import { useModalBehavior } from "@/hooks/useModalBehavior";

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
  reviewStatus: "pending_review" | null;
}

type TypeFilter = "all" | "video" | "image" | "audio";
const TYPE_FILTER_IDS: TypeFilter[] = ["all", "video", "image", "audio"];
const AI_GENERATED_CATEGORIES = new Set([
  "audio",
  "character_identity",
  "gpt_images",
  "keyframes",
  "pending_review",
  "seedance",
  "thumbnails",
]);

function isVideoMime(m: string) { return m.startsWith("video/"); }
function isImageMime(m: string) { return m.startsWith("image/"); }
function isAudioMime(m: string) { return m.startsWith("audio/"); }
function isAiGeneratedCategory(category: string) { return AI_GENERATED_CATEGORIES.has(category); }

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
  const [failedUploads, setFailedUploads] = useState<{ file: File; error: string }[]>([]);
  const [preview, setPreview] = useState<MaterialAsset | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const previewCloseRef = useRef<HTMLButtonElement>(null);
  const uploadAbortRef = useRef<AbortController | null>(null);
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 24;

  const fetchAssets = useCallback(async (shouldCommit: () => boolean = () => true) => {
    setLoading(true);
    setError(null);

    if (isDemoMode()) {
      try {
        const { DEMO_FOOTAGE_ASSETS } = await import("@/demo-data");
        const mapped: MaterialAsset[] = (DEMO_FOOTAGE_ASSETS || []).map((a: Record<string, unknown>, i: number) => ({
          id: (a.asset_id as string) || `demo-${i}`,
          filename: a.filename as string,
          originalName: (a.original_name as string) || (a.filename as string),
          filePath: a.file_path as string,
          sizeBytes: (a.file_size as number) || 0,
          mimeType: (a.mime_type as string) || "application/octet-stream",
          thumbnailPath: (a.thumbnail_path as string | null) || null,
          tags: (a.tags as string[]) || [],
          producedAt: ((a.metadata as Record<string, unknown> | undefined)?.uploaded_at as string) || new Date().toISOString(),
          isAiGenerated: ((a.tags as string[]) || []).some((tg: string) => tg.includes("ai-") || tg.includes("seedance")),
          reviewStatus: null,
        }));
        if (shouldCommit()) {
          setAssets(mapped.filter((m) => !isVideoMime(m.mimeType) || m.sizeBytes === 0 || m.tags.every((t) => t !== "renders")));
        }
      } catch (e: unknown) {
        if (shouldCommit()) setError(errorMessage(e, t("common.fetchFailed")));
      } finally {
        if (shouldCommit()) setLoading(false);
      }
      return;
    }

    try {
      const res = await apiFetch("/portfolio/?kind=creation_intermediate&limit=500&sort=size_desc");
      if (!res.ok) {
        const fallback = await apiFetch("/portfolio/?limit=500&sort=size_desc");
        if (!fallback.ok) throw new Error(`${t("common.fetchFailed")} (${fallback.status})`);
        const data = await fallback.json();
        const mapped: MaterialAsset[] = (data.files || [])
          .filter((f: Record<string, unknown>) => f.category !== "renders" && f.category !== "fast_mode")
          .map((f: Record<string, unknown>) => ({
            id: f.id as string,
            filename: f.filename as string,
            originalName: f.filename as string,
            filePath: f.path as string,
            sizeBytes: f.size_bytes as number,
            mimeType: f.mime_type as string,
            thumbnailPath: f.thumbnail_path as string | null,
            tags: [f.category as string],
            producedAt: f.produced_at as string,
            isAiGenerated: isAiGeneratedCategory(f.category as string),
            reviewStatus: (f.review_status as MaterialAsset["reviewStatus"]) ?? null,
          }));
        if (shouldCommit()) setAssets(mapped);
        return;
      }
      const data = await res.json();
      const mapped: MaterialAsset[] = (data.files || []).map((f: Record<string, unknown>) => ({
        id: f.id as string,
        filename: f.filename as string,
        originalName: f.filename as string,
        filePath: f.path as string,
        sizeBytes: f.size_bytes as number,
        mimeType: f.mime_type as string,
        thumbnailPath: f.thumbnail_path as string | null,
        tags: [f.category as string],
        producedAt: f.produced_at as string,
        isAiGenerated: isAiGeneratedCategory(f.category as string),
        reviewStatus: (f.review_status as MaterialAsset["reviewStatus"]) ?? null,
      }));
      if (shouldCommit()) setAssets(mapped);
    } catch (e: unknown) {
      if (shouldCommit()) setError(errorMessage(e, t("common.fetchFailed")));
    } finally {
      if (shouldCommit()) setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchAssets(() => !cancelled);
    return () => { cancelled = true; };
  }, [fetchAssets]);

  useEffect(() => () => {
    uploadAbortRef.current?.abort();
  }, []);

  const closePreview = () => setPreview(null);

  useModalBehavior({
    open: Boolean(preview),
    onClose: closePreview,
    initialFocusRef: previewCloseRef,
  });

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

  const totalPages = Math.max(1, Math.ceil(filteredAssets.length / PAGE_SIZE));
  const safePage = Math.min(Math.max(1, page), totalPages);
  const pagedAssets = useMemo(() => {
    const start = (safePage - 1) * PAGE_SIZE;
    return filteredAssets.slice(start, start + PAGE_SIZE);
  }, [filteredAssets, safePage]);

  const handleFilterChange = (next: TypeFilter) => {
    setTypeFilter(next);
    setPage(1);
  };
  const handleSearchChange = (q: string) => {
    setSearchQuery(q);
    setPage(1);
  };

  const uploadFiles = async (files: File[]) => {
    if (uploading) return;
    if (isDemoMode()) {
      setError(t("library.demoModeUploadDisabled"));
      return;
    }
    setUploading(true);
    setError(null);
    const controller = new AbortController();
    uploadAbortRef.current = controller;
    const newFailures: { file: File; error: string }[] = [];
    let completedCount = 0;
    try {
      for (let i = 0; i < files.length; i++) {
        if (controller.signal.aborted) break;
        const file = files[i];
        setUploadProgress(`${t("footage.uploading")} (${i + 1}${t("footage.of")}${files.length}): ${file.name}`);
        try {
          const formData = new FormData();
          formData.append("file", file);
          formData.append("tags", "materials,user_upload");
          formData.append("metadata", JSON.stringify({ source: "library-materials" }));
          const res = await apiFetch("/api/upload", { method: "POST", body: formData, signal: controller.signal });
          if (!res.ok) throw new Error(`${t("footage.uploadFailed")} (${res.status})`);
          completedCount += 1;
        } catch (e: unknown) {
          if (controller.signal.aborted) break;
          newFailures.push({ file, error: errorMessage(e, t("footage.uploadFailed")) });
        }
      }
    } finally {
      if (uploadAbortRef.current === controller) uploadAbortRef.current = null;
      setUploadProgress(null);
      setUploading(false);
    }
    if (newFailures.length > 0) {
      setFailedUploads((prev) => [...prev, ...newFailures]);
    }
    if (!controller.signal.aborted || completedCount > 0) {
      await fetchAssets();
    }
  };

  const retryFailedUploads = async () => {
    const filesToRetry = failedUploads.map((f) => f.file);
    setFailedUploads([]);
    await uploadFiles(filesToRetry);
  };

  const dismissFailedUploads = () => {
    setFailedUploads([]);
  };

  const cancelUpload = () => {
    uploadAbortRef.current?.abort();
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
                onClick={() => handleFilterChange(id)}
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
            onChange={(e) => handleSearchChange(e.target.value)}
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
          <span className="text-xs text-[var(--jade-accent)] font-medium flex-1">{uploadProgress || t("footage.uploadProgress")}</span>
          <button
            type="button"
            onClick={cancelUpload}
            className="apple-btn text-xs py-1 px-2 border border-[var(--border-default)]"
          >
            {t("upload.cancel", "取消上传")}
          </button>
        </div>
      )}

      {failedUploads.length > 0 && !uploading && (
        <div
          role="alert"
          className="apple-card p-3 border-l-4 border-[var(--crimson-mist)] bg-[rgba(196,91,80,0.06)] space-y-2"
        >
          <div className="flex items-start gap-2">
            <WarningCircle size={16} weight="fill" className="text-[var(--crimson-mist)] shrink-0 mt-0.5" />
            <div className="flex-1 min-w-0 text-xs">
              <p className="font-medium text-[var(--crimson-mist)]">
                {t("upload.someFailed", "{count} 个文件上传失败").replace(
                  "{count}",
                  String(failedUploads.length),
                )}
              </p>
              <ul className="mt-1 space-y-0.5 text-[var(--text-muted)] truncate">
                {failedUploads.slice(0, 3).map((f, i) => (
                  <li key={`${f.file.name}-${i}`} className="truncate">
                    · {f.file.name} — {f.error}
                  </li>
                ))}
                {failedUploads.length > 3 && (
                  <li className="text-[var(--text-muted)]">
                    {t("upload.andMore", "及其余 {count} 个").replace(
                      "{count}",
                      String(failedUploads.length - 3),
                    )}
                  </li>
                )}
              </ul>
            </div>
          </div>
          <div className="flex gap-2 justify-end">
            <button
              type="button"
              onClick={dismissFailedUploads}
              className="apple-btn text-xs py-1.5 px-3 border border-[var(--border-default)]"
            >
              {t("upload.dismissFailed", "忽略")}
            </button>
            <button
              type="button"
              onClick={retryFailedUploads}
              className="apple-btn apple-btn-primary text-xs py-1.5 px-3"
            >
              {t("upload.retryFailed", "重试上传")}
            </button>
          </div>
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
        <>
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
          {pagedAssets.map((asset) => {
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
                data-review-status={asset.reviewStatus ?? undefined}
                onClick={() => setPreview(asset)}
                className="apple-card overflow-hidden cursor-pointer transition-all duration-200 hover:shadow-md group text-left"
              >
                <div className="aspect-video bg-[var(--cinema-black)] relative flex items-center justify-center overflow-hidden">
                  {isImage && url ? (
                    <RuntimeMediaImage src={url} alt={asset.originalName} className="w-full h-full object-cover" />
                  ) : isVideo ? (
                    thumb ? (
                      <RuntimeMediaImage src={thumb} alt={asset.originalName} className="w-full h-full object-cover" />
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
                    {asset.reviewStatus === "pending_review" && (
                      <span className="text-[11px] px-1.5 py-0.5 rounded-full bg-[rgba(199,151,76,0.16)] text-[var(--gold-foil)] font-medium">
                        {t("library.materials.pendingReview")}
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
        <Pagination
          page={safePage}
          pageSize={PAGE_SIZE}
          total={filteredAssets.length}
          onPageChange={setPage}
        />
        </>
      )}

      {preview && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={preview.originalName}
          className="fixed inset-0 z-[200] flex items-center justify-center bg-black/85 backdrop-blur-sm"
          onClick={closePreview}
        >
          <div className="relative max-w-[90vw] max-h-[90vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
            <button
              ref={previewCloseRef}
              onClick={closePreview}
              className="absolute -top-10 right-0 p-2 rounded-full bg-white/10 text-white/80 hover:bg-white/20 hover:text-white transition-all cursor-pointer z-10"
              aria-label={t("common.close")}
            >
              <X size={20} weight="fill" />
            </button>
            <div className="rounded-xl overflow-hidden bg-black/60">
              {isVideoMime(preview.mimeType) ? (
                <video
                  src={getMediaUrl(preview.filePath)}
                  poster={preview.thumbnailPath ? getMediaUrl(preview.thumbnailPath) : undefined}
                  controls
                  autoPlay
                  muted
                  playsInline
                  preload="metadata"
                  className="max-w-[85vw] max-h-[75vh] object-contain"
                />
              ) : isImageMime(preview.mimeType) ? (
                <RuntimeMediaImage src={getMediaUrl(preview.filePath)} alt={preview.originalName} className="max-w-[85vw] max-h-[75vh] object-contain" />
              ) : (
                <div className="px-12 py-16 text-center">
                  <MusicNotes size={48} weight="fill" className="text-white/40 mx-auto mb-4" />
                  <audio src={getMediaUrl(preview.filePath)} controls preload="metadata" className="w-64" />
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
