"use client";

import { useEffect, useMemo, useState } from "react";
import { useI18n } from "@/i18n/I18nProvider";
import { apiFetch, getMediaUrl } from "./api";
import { MagnifyingGlass, X, Check, FilmSlate, ImageSquare, MusicNote } from "@phosphor-icons/react";
import RuntimeMediaImage from "./RuntimeMediaImage";

export type AcceptKind = "image" | "video" | "audio" | "all";

interface PortfolioFile {
  id: string;
  filename: string;
  path: string;
  label: string | null;
  scenario: string | null;
  produced_at: string;
  size_bytes: number;
  mime_type: string;
  thumbnail_path: string | null;
}

interface Props {
  acceptKind: AcceptKind;
  multiple?: boolean;
  onPick: (mediaUrls: string[]) => void;
  onClose: () => void;
}

const KIND_ICONS = {
  video: FilmSlate,
  image: ImageSquare,
  audio: MusicNote,
};

function mimeMatchesKind(mime: string, kind: AcceptKind): boolean {
  if (kind === "all") return mime.startsWith("video/") || mime.startsWith("image/") || mime.startsWith("audio/");
  return mime.startsWith(`${kind}/`);
}

function humanSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function AssetPickerModal({ acceptKind, multiple = false, onPick, onClose }: Props) {
  const { t } = useI18n();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [files, setFiles] = useState<PortfolioFile[]>([]);
  const [query, setQuery] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await apiFetch("/portfolio/?limit=200&sort=recent");
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (cancelled) return;
        const all: PortfolioFile[] = (data.files || []).filter((f: PortfolioFile) =>
          mimeMatchesKind(f.mime_type || "", acceptKind),
        );
        setFiles(all);
      } catch (e: unknown) {
        if (!cancelled) setError(e instanceof Error ? e.message : t("picker.loadFailed"));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [acceptKind, t]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return files;
    return files.filter(
      (f) =>
        f.filename.toLowerCase().includes(q) ||
        (f.label || "").toLowerCase().includes(q) ||
        (f.scenario || "").toLowerCase().includes(q),
    );
  }, [files, query]);

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        if (!multiple) next.clear();
        next.add(id);
      }
      return next;
    });
  };

  const handleConfirm = () => {
    const picked = filtered.filter((f) => selectedIds.has(f.id));
    const urls = picked.map((f) => getMediaUrl(f.path));
    onPick(urls);
    onClose();
  };

  const kindLabel =
    acceptKind === "video"
      ? t("picker.kind.video")
      : acceptKind === "image"
        ? t("picker.kind.image")
        : acceptKind === "audio"
          ? t("picker.kind.audio")
          : t("picker.kind.all");

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/60 backdrop-blur-sm px-4">
      <div className="apple-card w-full max-w-5xl max-h-[85vh] flex flex-col overflow-hidden">
        <header className="flex items-center justify-between px-5 py-3 border-b border-[var(--border-default)]">
          <div className="flex items-center gap-3 min-w-0">
            <h3 className="text-sm font-semibold text-[var(--text-h1)] shrink-0">
              {t("picker.title")}
            </h3>
            <span className="text-[11px] text-[var(--text-muted)] px-2 py-0.5 rounded-full bg-[var(--bg-panel)] shrink-0">
              {kindLabel}
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="p-1.5 rounded-lg hover:bg-[var(--bg-panel)] text-[var(--text-muted)] hover:text-[var(--text-h1)] transition-colors"
          >
            <X size={16} weight="bold" />
          </button>
        </header>

        <div className="px-5 py-3 border-b border-[var(--border-default)]">
          <div className="relative">
            <MagnifyingGlass
              size={14}
              weight="fill"
              className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
            />
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t("picker.searchPlaceholder")}
              className="apple-input text-sm pl-9 pr-3 w-full"
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {loading ? (
            <div
              className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3"
              aria-busy="true"
              aria-live="polite"
            >
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="apple-card overflow-hidden">
                  <div className="aspect-video skeleton" />
                  <div className="p-3 space-y-1.5">
                    <div className="h-3 w-3/4 skeleton rounded" />
                    <div className="h-2 w-1/2 skeleton rounded" />
                  </div>
                </div>
              ))}
            </div>
          ) : error ? (
            <div className="py-10 text-center text-sm text-[var(--neon-red)]">{error}</div>
          ) : filtered.length === 0 ? (
            <div className="py-10 text-center text-sm text-[var(--text-muted)]">
              {query ? t("picker.noMatch") : t("picker.empty")}
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
              {filtered.map((file) => {
                const selected = selectedIds.has(file.id);
                const kind = file.mime_type.startsWith("video/")
                  ? "video"
                  : file.mime_type.startsWith("image/")
                    ? "image"
                    : "audio";
                const Icon = KIND_ICONS[kind];
                const thumbUrl = file.thumbnail_path ? getMediaUrl(file.thumbnail_path) : "";
                const previewUrl = kind === "image" ? getMediaUrl(file.path) : thumbUrl;
                return (
                  <button
                    key={file.id}
                    type="button"
                    onClick={() => toggleSelect(file.id)}
                    className={`apple-card overflow-hidden text-left transition-all cursor-pointer ${
                      selected
                        ? "ring-2 ring-[var(--fortune-red)] shadow-md"
                        : "hover:shadow-md"
                    }`}
                  >
                    <div className="aspect-video bg-[var(--cinema-black)] relative flex items-center justify-center overflow-hidden">
                      {previewUrl ? (
                        <RuntimeMediaImage
                          src={previewUrl}
                          alt={file.filename}
                          className="w-full h-full object-cover"
                        />
                      ) : (
                        <div className="w-full h-full bg-[var(--bg-panel)] flex items-center justify-center">
                          <Icon size={28} weight="fill" className="text-[var(--text-muted)]" />
                        </div>
                      )}
                      {selected && (
                        <div className="absolute top-1.5 right-1.5 w-6 h-6 rounded-full bg-[var(--fortune-red)] flex items-center justify-center shadow">
                          <Check size={12} weight="bold" className="text-white" />
                        </div>
                      )}
                    </div>
                    <div className="p-2">
                      <p className="text-[12px] font-medium text-[var(--text-h1)] truncate">
                        {file.label || file.filename}
                      </p>
                      <p className="text-[11px] text-[var(--text-muted)] mt-0.5">
                        {humanSize(file.size_bytes)}
                      </p>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        <footer className="flex items-center justify-between px-5 py-3 border-t border-[var(--border-default)]">
          <span className="text-[12px] text-[var(--text-muted)]">
            {selectedIds.size > 0 ? `${t("picker.selectedPrefix")} ${selectedIds.size}` : t("picker.selectHint")}
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-3 py-1.5 rounded-lg text-[12px] text-[var(--text-muted)] hover:bg-[var(--bg-panel)] hover:text-[var(--text-h1)] transition-colors"
            >
              {t("picker.cancel")}
            </button>
            <button
              type="button"
              onClick={handleConfirm}
              disabled={selectedIds.size === 0}
              className="px-4 py-1.5 rounded-lg text-[12px] font-medium bg-[var(--fortune-red)] text-white hover:bg-[var(--fortune-red-600)] active:scale-[0.98] transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {t("picker.confirm")}
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}
