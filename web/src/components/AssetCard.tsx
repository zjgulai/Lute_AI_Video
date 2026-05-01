"use client";

import React from "react";
import { useI18n } from "@/i18n/I18nProvider";
import { getMediaUrl } from "./api";
import { Play, Article, MusicNotes, Image, VideoCamera, FileImage } from "@phosphor-icons/react";

export type AssetType = "video" | "image" | "audio" | "text";
export type AssetSource = "ai" | "manual" | "imported";

export interface AssetItem {
  id: string;
  type: AssetType;
  source: AssetSource;
  title: string;
  thumbnail?: string;
  filePath?: string;
  duration?: number;
  textContent?: string;
  createdAt: string;
  metadata?: Record<string, any>;
}

interface Props {
  asset: AssetItem;
  onClick?: (asset: AssetItem) => void;
}

const SOURCE_COLORS: Record<AssetSource, string> = {
  ai: "bg-[rgba(215,92,112,0.10)] text-[var(--fortune-red)]",
  manual: "bg-[rgba(220,190,120,0.10)] text-[var(--gold-foil)]",
  imported: "bg-[rgba(155,124,196,0.10)] text-[var(--cinema-violet)]",
};

const SOURCE_LABELS: Record<AssetSource, string> = {
  ai: "brand.filter.ai",
  manual: "brand.filter.manual",
  imported: "brand.filter.imported",
};

export default function AssetCard({ asset, onClick }: Props) {
  const { t } = useI18n();

  const handleClick = () => onClick?.(asset);

  switch (asset.type) {
    case "video":
      return <VideoCard asset={asset} onClick={handleClick} t={t} />;
    case "image":
      return <ImageCard asset={asset} onClick={handleClick} t={t} />;
    case "audio":
      return <AudioCard asset={asset} onClick={handleClick} t={t} />;
    case "text":
      return <TextCard asset={asset} onClick={handleClick} t={t} />;
    default:
      return null;
  }
}

function VideoCard({ asset, onClick, t }: { asset: AssetItem; onClick: () => void; t: (k: string) => string }) {
  return (
    <div
      onClick={onClick}
      className="apple-card overflow-hidden cursor-pointer group hover:shadow-md transition-all duration-200"
    >
      {/* Thumbnail — 3:2 ratio */}
      <div className="relative aspect-[3/2] bg-black overflow-hidden">
        {asset.thumbnail ? (
          <video
            src={getMediaUrl(asset.thumbnail)}
            className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
            preload="metadata"
            muted
            playsInline
          />
        ) : (
          <div className="w-full h-full bg-[var(--color-bg-secondary)] flex items-center justify-center">
            <VideoCamera size={24} weight="fill" className="text-[var(--color-text-tertiary)]" />
          </div>
        )}
        <div className="absolute inset-0 flex items-center justify-center bg-black/0 group-hover:bg-black/20 transition-all">
          <div className="w-10 h-10 rounded-full bg-white/90 flex items-center justify-center shadow-lg opacity-0 group-hover:opacity-100 transition-all scale-90 group-hover:scale-100">
            <Play size={18} weight="fill" className="text-[var(--color-text-primary)] ml-0.5" />
          </div>
        </div>
        {asset.duration !== undefined && asset.duration > 0 && (
          <div className="absolute bottom-2 right-2 px-1.5 py-0.5 rounded bg-black/60 text-white text-[10px]">
            {asset.duration}s
          </div>
        )}
      </div>
      {/* Info */}
      <div className="p-3">
        <h4 className="text-xs font-semibold text-[var(--color-text-primary)] truncate">{asset.title}</h4>
        <div className="flex items-center gap-2 mt-1.5">
          <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${SOURCE_COLORS[asset.source]}`}>
            {t(SOURCE_LABELS[asset.source])}
          </span>
          <span className="text-[10px] text-[var(--color-text-tertiary)]">
            {formatDate(asset.createdAt)}
          </span>
        </div>
      </div>
    </div>
  );
}

function ImageCard({ asset, onClick, t }: { asset: AssetItem; onClick: () => void; t: (k: string) => string }) {
  return (
    <div
      onClick={onClick}
      className="apple-card overflow-hidden cursor-pointer group hover:shadow-md transition-all duration-200"
    >
      {/* Square thumbnail */}
      <div className="relative aspect-square bg-[var(--color-bg-secondary)] overflow-hidden">
        {asset.thumbnail || asset.filePath ? (
          <img
            src={(() => {
              const raw = asset.thumbnail || asset.filePath || "";
              return raw.startsWith("/") && !raw.startsWith("/api/")
                ? raw
                : getMediaUrl(raw);
            })()}
            alt={asset.title}
            className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
            loading="lazy"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <FileImage size={24} weight="fill" className="text-[var(--color-text-tertiary)]" />
          </div>
        )}
      </div>
      {/* Info */}
      <div className="p-3">
        <h4 className="text-xs font-semibold text-[var(--color-text-primary)] truncate">{asset.title}</h4>
        <div className="flex items-center gap-2 mt-1.5">
          <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${SOURCE_COLORS[asset.source]}`}>
            {t(SOURCE_LABELS[asset.source])}
          </span>
          <span className="text-[10px] text-[var(--color-text-tertiary)]">
            {formatDate(asset.createdAt)}
          </span>
        </div>
      </div>
    </div>
  );
}

function AudioCard({ asset, onClick, t }: { asset: AssetItem; onClick: () => void; t: (k: string) => string }) {
  return (
    <div
      onClick={onClick}
      className="apple-card p-3 cursor-pointer hover:shadow-md transition-all duration-200"
    >
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-[rgba(220,190,120,0.10)] flex items-center justify-center shrink-0">
          <MusicNotes size={18} weight="fill" className="text-[var(--gold-foil)]" />
        </div>
        <div className="flex-1 min-w-0">
          <h4 className="text-xs font-semibold text-[var(--color-text-primary)] truncate">{asset.title}</h4>
          <div className="flex items-center gap-2 mt-1">
            <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${SOURCE_COLORS[asset.source]}`}>
              {t(SOURCE_LABELS[asset.source])}
            </span>
            <span className="text-[10px] text-[var(--color-text-tertiary)]">
              {formatDate(asset.createdAt)}
            </span>
          </div>
        </div>
      </div>
      {/* Waveform placeholder */}
      <div className="mt-2 h-6 flex items-end gap-[2px]">
        {Array.from({ length: 24 }).map((_, i) => {
          const h = 30 + Math.sin(i * 0.8) * 20 + Math.random() * 30;
          return (
            <div
              key={i}
              className="flex-1 rounded-full bg-[var(--color-accent)]/20"
              style={{ height: `${Math.min(100, h)}%` }}
            />
          );
        })}
      </div>
    </div>
  );
}

function TextCard({ asset, onClick, t }: { asset: AssetItem; onClick: () => void; t: (k: string) => string }) {
  return (
    <div
      onClick={onClick}
      className="apple-card p-3 cursor-pointer hover:shadow-md transition-all duration-200"
    >
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-xl bg-[rgba(155,124,196,0.10)] flex items-center justify-center shrink-0">
          <Article size={18} weight="fill" className="text-[var(--cinema-violet)]" />
        </div>
        <div className="flex-1 min-w-0">
          <h4 className="text-xs font-semibold text-[var(--color-text-primary)] truncate">{asset.title}</h4>
          <p className="text-[11px] text-[var(--color-text-secondary)] line-clamp-2 mt-1">
            {asset.textContent || "—"}
          </p>
          <div className="flex items-center gap-2 mt-1.5">
            <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${SOURCE_COLORS[asset.source]}`}>
              {t(SOURCE_LABELS[asset.source])}
            </span>
            <span className="text-[10px] text-[var(--color-text-tertiary)]">
              {formatDate(asset.createdAt)}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("zh-CN", { month: "short", day: "numeric" });
  } catch {
    return iso;
  }
}
