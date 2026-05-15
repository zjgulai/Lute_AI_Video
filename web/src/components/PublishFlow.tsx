"use client";

import React, { useState, useMemo } from "react";
import { useI18n } from "@/i18n/I18nProvider";
import { publishVideo } from "./api";
import { PaperPlaneRight, CheckCircle, ArrowCounterClockwise } from "@phosphor-icons/react";

import { errorMessage } from "@/lib/errors";
interface Props {
  result: any;
}

const ALL_PLATFORMS = [
  { id: "tiktok", color: "#000000" },
  { id: "instagram", color: "#E4405F" },
  { id: "youtube_shorts", color: "#FF0000" },
  { id: "shopify", color: "#96BF48" },
  { id: "amazon", color: "#FF9900" },
  { id: "facebook", color: "#1877F2" },
];

export default function PublishFlow({ result }: Props) {
  const { t } = useI18n();
  const [selectedPlatforms, setSelectedPlatforms] = useState<Set<string>>(new Set());
  const [publishing, setPublishing] = useState(false);
  const [publishedPlatforms, setPublishedPlatforms] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

  // AI-recommended platforms based on briefs
  const recommendedPlatforms = useMemo(() => {
    const briefs = result?.briefs || [];
    const platformsFromBriefs = briefs
      .map((b: any) => b.platform)
      .filter(Boolean);
    const unique = Array.from(new Set(platformsFromBriefs));
    return unique.length > 0 ? unique : ["tiktok", "shopify"];
  }, [result]);

  // Auto-fill metadata from result
  const metadata = useMemo(() => {
    const brief = result?.briefs?.[0] || {};
    const script = result?.scripts?.[0] || {};
    const segments = script.segments || [];

    const title = brief.product_name || brief.brand_name || script.product_name || "";
    const description = brief.key_message || brief.description || segments.slice(0, 3).map((s: any) => s.voiceover).join(" ") || "";
    const tags = brief.tags || brief.usp_priority || [];

    return { title, description, tags };
  }, [result]);

  const togglePlatform = (platformId: string) => {
    if (publishing || publishedPlatforms.has(platformId)) return;
    setSelectedPlatforms((prev) => {
      const next = new Set(prev);
      if (next.has(platformId)) next.delete(platformId);
      else next.add(platformId);
      return next;
    });
  };

  const handlePublish = async () => {
    if (selectedPlatforms.size === 0) return;
    setPublishing(true);
    setError(null);

    try {
      const videoPath = result?.final_video_path || "";
      const videoId = videoPath.split("/").pop()?.split(".")[0] || videoPath;

      const results = await publishVideo(
        videoId,
        Array.from(selectedPlatforms),
        {
          title: metadata.title,
          description: metadata.description,
          hashtags: metadata.tags,
          product_name: metadata.title,
        }
      );

      const resultsArray = Array.isArray(results) ? results : [results];
      const successful = resultsArray
        .filter((r: any) => r.success)
        .map((r: any) => r.platform);

      setPublishedPlatforms(new Set(successful));
    } catch (err: unknown) {
      setError(errorMessage(err, t("common.fetchFailed")));
    } finally {
      setPublishing(false);
    }
  };

  const allPublished = selectedPlatforms.size > 0 &&
    Array.from(selectedPlatforms).every((p) => publishedPlatforms.has(p));

  return (
    <div className="space-y-4">
      {/* AI Recommended Platforms */}
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <span className="text-[12px] font-medium text-[var(--color-accent)] uppercase tracking-wider">
            {t("publish.platformRecommend")}
          </span>
          <span className="text-[12px] text-[var(--color-text-tertiary)]">
            {t("publish.subtitle")}
          </span>
        </div>
        <div className="flex flex-wrap gap-2">
          {ALL_PLATFORMS.map((platform) => {
            const isRecommended = recommendedPlatforms.includes(platform.id);
            const isSelected = selectedPlatforms.has(platform.id);
            const isPublished = publishedPlatforms.has(platform.id);
            const disabled = publishing || isPublished;

            return (
              <button
                key={platform.id}
                onClick={() => togglePlatform(platform.id)}
                disabled={disabled}
                className={`relative flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all cursor-pointer border ${
                  isPublished
                    ? "bg-[rgba(120,175,140,0.10)] border-[var(--jade-accent)] text-[var(--jade-accent)]"
                    : isSelected
                    ? "bg-[var(--color-accent)]/10 border-[var(--color-accent)] text-[var(--color-accent)]"
                    : "bg-[var(--bg-card)] border-[var(--color-border-light)] text-[var(--color-text-secondary)] hover:border-[var(--color-accent)]/30"
                } ${disabled ? "opacity-60 cursor-not-allowed" : ""}`}
              >
                {isPublished && <CheckCircle size={12} weight="fill" />}
                {t("platform." + platform.id)}
                {isRecommended && !isSelected && !isPublished && (
                  <span className="absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full bg-[var(--color-accent)] text-white text-[8px] flex items-center justify-center">
                    AI
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Auto-filled Metadata */}
      <div className="space-y-3">
        <div>
          <label className="text-[12px] font-medium text-[var(--color-text-tertiary)] uppercase tracking-wider block mb-1">
            {t("publish.titleLabel")}
          </label>
          <div className="text-sm text-[var(--color-text-primary)] bg-[var(--color-bg-secondary)] px-3 py-2 rounded-lg border border-[var(--color-border-light)]">
            {metadata.title || <span className="text-[var(--color-text-tertiary)] italic">{t("publish.titlePlaceholder")}</span>}
          </div>
        </div>

        <div>
          <label className="text-[12px] font-medium text-[var(--color-text-tertiary)] uppercase tracking-wider block mb-1">
            {t("publish.descriptionLabel")}
          </label>
          <div className="text-xs text-[var(--color-text-primary)] bg-[var(--color-bg-secondary)] px-3 py-2 rounded-lg border border-[var(--color-border-light)] line-clamp-3">
            {metadata.description || <span className="text-[var(--color-text-tertiary)] italic">{t("publish.descriptionPlaceholder")}</span>}
          </div>
        </div>

        {metadata.tags.length > 0 && (
          <div>
            <label className="text-[12px] font-medium text-[var(--color-text-tertiary)] uppercase tracking-wider block mb-1">
              {t("publish.tagsLabel")}
            </label>
            <div className="flex flex-wrap gap-1">
              {metadata.tags.map((tag: string, i: number) => (
                <span key={i} className="text-[12px] px-2 py-0.5 rounded-full bg-[var(--color-accent)]/10 text-[var(--color-accent)]">
                  #{tag}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="text-xs text-[var(--color-error)] bg-[var(--color-error)]/5 px-3 py-2 rounded-lg flex items-center gap-2">
          <ArrowCounterClockwise size={12} weight="fill" />
          {error}
        </div>
      )}

      {/* Publish Button */}
      {!allPublished ? (
        <button
          onClick={handlePublish}
          disabled={selectedPlatforms.size === 0 || publishing}
          className="apple-btn apple-btn-primary w-full gap-2 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {publishing ? (
            <>
              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              {t("publish.publishing")}
            </>
          ) : (
            <>
              <PaperPlaneRight size={14} weight="fill" />
              {t("publish.publishBtn")}
            </>
          )}
        </button>
      ) : (
        <div className="flex items-center justify-center gap-2 text-sm text-[var(--jade-accent)] font-medium py-2">
          <CheckCircle size={16} weight="fill" />
          {t("publish.success")}
        </div>
      )}
    </div>
  );
}
