"use client";

import { useState, useRef, useCallback } from "react";
import { useI18n } from "@/i18n/I18nProvider";
import { API_BASE } from "./api";

const ACCEPT_TYPES = {
  video: ".mp4,.mov,.webm",
  image: ".png,.jpg,.jpeg,.webp",
  audio: ".mp3,.wav,.m4a",
  document: ".pdf,.doc,.docx,.txt,.md",
};

interface UploadResult {
  filename: string;
  path: string;
  size: number;
}

interface Props {
  onUpload?: (results: UploadResult[]) => void;
}

export default function AssetUploader({ onUpload }: Props) {
  const { t } = useI18n();
  const [dragActive, setDragActive] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [results, setResults] = useState<UploadResult[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files?.length) {
      uploadFiles(e.dataTransfer.files);
    }
  }, []);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.length) {
      uploadFiles(e.target.files);
    }
  };

  const uploadFiles = async (files: FileList) => {
    setUploading(true);
    const uploaded: UploadResult[] = [];

    for (const file of Array.from(files)) {
      const formData = new FormData();
      formData.append("file", file);

      try {
        const res = await fetch(API_BASE + "/api/upload", {
          method: "POST",
          body: formData,
        });
        if (res.ok) {
          const data = await res.json();
          uploaded.push(data);
        }
      } catch (e) {
        console.error("Upload failed", e);
      }
    }

    setResults(uploaded);
    setUploading(false);
    onUpload?.(uploaded);
  };

  const getFileIcon = (filename: string) => {
    const ext = filename.split(".").pop()?.toLowerCase() || "";
    if (["mp4", "mov", "webm"].includes(ext)) return "🎬";
    if (["png", "jpg", "jpeg", "webp"].includes(ext)) return "🖼️";
    if (["mp3", "wav", "m4a"].includes(ext)) return "🎵";
    return "📄";
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  };

  return (
    <div className="space-y-3">
      {/* Drop zone */}
      <div
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        className={`apple-card p-6 text-center cursor-pointer transition-all ${
          dragActive
            ? "border-2 border-dashed border-[var(--fortune-red)] bg-[rgba(215,92,112,0.05)]"
            : "border-2 border-dashed border-[var(--border-default)] hover:border-[var(--border-default)]"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          multiple
          className="hidden"
          onChange={handleChange}
          accept={Object.values(ACCEPT_TYPES).join(",")}
        />
        <div className="w-12 h-12 rounded-2xl bg-[var(--bg-card)] flex items-center justify-center mx-auto mb-3">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="1.5">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17 8 12 3 7 8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
        </div>
        <p className="text-sm font-medium text-[var(--text-h1)]">
          {uploading ? t("upload.uploading") : dragActive ? t("upload.dragActive") : t("upload.dragInactive")}
        </p>
        <p className="text-[11px] text-[var(--text-muted)] mt-1">
          {t("upload.hint")}
        </p>
      </div>

      {/* Upload results */}
      {results.length > 0 && (
        <div className="apple-card p-3 bg-[var(--bg-card)]">
          <p className="text-[10px] font-mono text-[var(--text-muted)] mb-2">{t("upload.uploaded")} ({results.length})</p>
          <div className="space-y-1.5">
            {results.map((r, i) => (
              <div key={i} className="flex items-center gap-2 bg-[var(--bg-card)] rounded-lg p-2 border border-[var(--border-default)]">
                <span className="text-base">{getFileIcon(r.filename)}</span>
                <div className="flex-1 min-w-0">
                  <p className="text-[11px] text-[var(--text-h1)] truncate">{r.filename}</p>
                  <p className="text-[9px] text-[var(--text-muted)]">{formatSize(r.size)}</p>
                </div>
                <span className="text-[10px] text-[var(--fortune-red)] font-medium">{t("upload.saved")}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
