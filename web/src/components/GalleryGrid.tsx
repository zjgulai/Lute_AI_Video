"use client";

import React from "react";
import { useI18n } from "@/i18n/I18nProvider";
import { getMediaUrl } from "./api";
import { Play, Clock, Eye, Heart, ShareNetwork, ChartBar } from "@phosphor-icons/react";
import RuntimeMediaImage from "./RuntimeMediaImage";

interface GalleryItem {
  id: string;
  title: string;
  scene: string;
  videoType: string;
  thumbnail: string;
  videoPath: string;
  duration: number;
  views?: number;
  likes?: number;
  shares?: number;
  score?: number;
  createdAt: string;
}

interface Props {
  items: GalleryItem[];
  onPlay?: (item: GalleryItem) => void;
}

const SCENE_ICONS: Record<string, string> = {
  product_direct: "🎯",
  live_shoot_to_video: "📹",
  brand_campaign: "🏛️",
  influencer_remix: "🎭",
  brand_vlog: "📖",
  quick_test: "⚡",
};

function formatViews(n?: number): string {
  if (!n) return "0";
  if (n >= 10000) return `${(n / 1000).toFixed(0)}K`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return n.toString();
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("zh-CN", { month: "short", day: "numeric" });
  } catch {
    return iso;
  }
}

export default function GalleryGrid({ items, onPlay }: Props) {
  const { t } = useI18n();

  if (items.length === 0) {
    return (
      <div className="apple-card p-12 text-center"
      >
        <div className="w-16 h-16 rounded-2xl bg-[var(--color-bg-secondary)] flex items-center justify-center mx-auto mb-4"
        >
          <Play size={28} weight="fill" className="text-[var(--color-text-tertiary)]" />
        </div>
        <p className="text-sm font-medium text-[var(--color-text-secondary)] mb-1">
          {t("gallery.emptyTitle") || "No finished works yet"}
        </p>
        <p className="text-xs text-[var(--color-text-tertiary)]">
          {t("gallery.emptyDesc") || "Create your first video and it will appear here"}
        </p>
      </div>
    );
  }

  // Group by scene
  const grouped = items.reduce((acc, item) => {
    const scene = item.scene || "other";
    if (!acc[scene]) acc[scene] = [];
    acc[scene].push(item);
    return acc;
  }, {} as Record<string, GalleryItem[]>);

  return (
    <div className="space-y-8">
      {Object.entries(grouped).map(([scene, sceneItems]) => (
        <div key={scene}
        >
          {/* Scene header */}
          <div className="flex items-center gap-2 mb-3"
          >
            <span className="text-lg">{SCENE_ICONS[scene] || "🎬"}</span>
            <span className="text-sm font-semibold text-[var(--color-text-primary)]">
              {t(`scene.${scene}.title`, t("scene.other.title", "未分类"))}
            </span>
            <span className="text-[12px] text-[var(--color-text-tertiary)]">({sceneItems.length})</span>
          </div>

          {/* 3-column card grid */}
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3"
          >
            {sceneItems.map((item) => (
              <div
                key={item.id}
                className="apple-card overflow-hidden cursor-pointer group hover:shadow-md transition-all duration-200"
                onClick={() => onPlay?.(item)}
              >
                {/* Thumbnail — 3:2 ratio */}
                <div className="relative aspect-[3/2] bg-black overflow-hidden"
                >
                  {item.thumbnail ? (
                    <RuntimeMediaImage
                      src={getMediaUrl(item.thumbnail)}
                      alt={item.title}
                      className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
                    />
                  ) : (
                    <div className="w-full h-full bg-[var(--color-bg-secondary)] flex items-center justify-center"
                    >
                      <Play size={24} weight="fill" className="text-[var(--color-text-tertiary)]" />
                    </div>
                  )}
                  {/* Play overlay */}
                  <div className="absolute inset-0 flex items-center justify-center bg-black/0 group-hover:bg-black/20 transition-all"
                  >
                    <div className="w-10 h-10 rounded-full bg-white/90 flex items-center justify-center shadow-lg opacity-0 group-hover:opacity-100 transition-all scale-90 group-hover:scale-100"
                    >
                      <Play size={18} weight="fill" className="text-[var(--color-text-primary)] ml-0.5" />
                    </div>
                  </div>
                  {/* Duration badge */}
                  {item.duration > 0 && (
                    <div className="absolute bottom-2 right-2 flex items-center gap-1 px-1.5 py-0.5 rounded bg-black/60 text-white text-[12px]"
                    >
                      <Clock size={10} weight="fill" />
                      {item.duration}s
                    </div>
                  )}
                  {/* Score badge */}
                  {item.score !== undefined && item.score > 0 && (
                    <div className="absolute top-2 left-2 flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-[rgba(120,175,140,0.90)] text-white text-[12px] font-medium"
                    >
                      <ChartBar size={10} weight="fill" />
                      {Math.round((item.score || 0) * 100)}%
                    </div>
                  )}
                </div>

                {/* Info */}
                <div className="p-3"
                >
                  <h4 className="text-xs font-semibold text-[var(--color-text-primary)] truncate mb-1"
                  >
                    {item.title}
                  </h4>
                  <div className="flex items-center justify-between"
                  >
                    <span className="text-[12px] text-[var(--color-text-tertiary)]"
                    >
                      {formatDate(item.createdAt)}
                    </span>
                    <div className="flex items-center gap-2 text-[12px] text-[var(--color-text-tertiary)]"
                    >
                      {item.views !== undefined && (
                        <span className="flex items-center gap-0.5"
                        >
                          <Eye size={10} weight="fill" /> {formatViews(item.views)}
                        </span>
                      )}
                      {item.likes !== undefined && (
                        <span className="flex items-center gap-0.5"
                        >
                          <Heart size={10} weight="fill" /> {formatViews(item.likes)}
                        </span>
                      )}
                      {item.shares !== undefined && (
                        <span className="flex items-center gap-0.5"
                        >
                          <ShareNetwork size={10} weight="fill" /> {formatViews(item.shares)}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
