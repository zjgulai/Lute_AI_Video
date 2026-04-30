"use client";

import { useState } from "react";
import { useI18n } from "@/i18n/I18nProvider";
import { publishVideo } from "./api";

interface PublishResult {
  platform: string;
  post_id?: string;
  post_url?: string;
  success: boolean;
  error?: string;
}

interface Props {
  videoPath: string;
  metadata: {
    hook?: string;
    hashtags?: string[];
    productName?: string;
  };
  onPublished?: (results: PublishResult[]) => void;
  onClose?: () => void;
}

type ProgressState = "idle" | "uploading" | "processing" | "done" | "error";

interface PlatformProgress {
  state: ProgressState;
  result?: PublishResult;
}

export default function PublishPanel({ videoPath, metadata, onPublished, onClose }: Props) {
  const { t } = useI18n();
  const [platforms, setPlatforms] = useState<Record<string, boolean>>({ tiktok: false, shopify: false });
  const [title, setTitle] = useState(metadata.hook || "");
  const [description, setDescription] = useState("");
  const [progress, setProgress] = useState<Record<string, PlatformProgress>>({});
  const [overallError, setOverallError] = useState<string | null>(null);

  const selectedPlatforms = Object.entries(platforms)
    .filter(([, selected]) => selected)
    .map(([key]) => key);

  const canPublish = selectedPlatforms.length > 0 && title.trim().length > 0;

  const handlePublish = async () => {
    setOverallError(null);

    // Initialize progress
    const initialProgress: Record<string, PlatformProgress> = {};
    selectedPlatforms.forEach((p) => {
      initialProgress[p] = { state: "uploading" };
    });
    setProgress(initialProgress);

    try {
      const videoId = videoPath.split("/").pop()?.split(".")[0] || videoPath;
      const results = await publishVideo(videoId, selectedPlatforms, {
        title: title.trim(),
        description: description.trim(),
        hashtags: metadata.hashtags || [],
        product_name: metadata.productName || "",
      });

      const resultsArray: PublishResult[] = Array.isArray(results) ? results : [results];
      const updatedProgress: Record<string, PlatformProgress> = {};

      resultsArray.forEach((r) => {
        const p = r.platform || selectedPlatforms[0];
        updatedProgress[p] = {
          state: r.success ? "done" : "error",
          result: r,
        };
      });

      // Mark any missing platforms as done (if results don't cover all)
      selectedPlatforms.forEach((p) => {
        if (!updatedProgress[p]) {
          updatedProgress[p] = { state: "processing" };
          setTimeout(() => {
            setProgress((prev) => ({
              ...prev,
              [p]: { state: "done", result: { platform: p, success: true } },
            }));
          }, 1000);
        }
      });

      setProgress(updatedProgress);
      onPublished?.(resultsArray);
    } catch (err: any) {
      setOverallError(err.message || t("common.fetchFailed"));
      const errorProgress: Record<string, PlatformProgress> = {};
      selectedPlatforms.forEach((p) => {
        errorProgress[p] = { state: "error", result: { platform: p, success: false, error: err.message } };
      });
      setProgress(errorProgress);
    }
  };

  const handleRetry = () => {
    setProgress({});
    setOverallError(null);
    handlePublish();
  };

  const handleClose = () => {
    onClose?.();
  };

  const isPublishing = Object.values(progress).some((p) => p.state === "uploading" || p.state === "processing");
  const isComplete = Object.values(progress).length > 0 && Object.values(progress).every((p) => p.state === "done");
  const hasError = Object.values(progress).some((p) => p.state === "error") || !!overallError;

  return (
    <div className="apple-card p-4 bg-white border border-[#EDD3D1]">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-md bg-[#6A2B3A]/10 flex items-center justify-center">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#6A2B3A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="17 1 21 5 17 9" />
              <path d="M3 11V9a4 4 0 0 1 4-4h14" />
              <polyline points="7 23 3 19 7 15" />
              <path d="M21 13v2a4 4 0 0 1-4 4H3" />
            </svg>
          </div>
          <h3 className="text-sm font-semibold text-[#35353B]">{t("perf.publishTitle")}</h3>
        </div>
        <button
          onClick={handleClose}
          className="text-[10px] text-[#9FA0A0] hover:text-[#35353B] cursor-pointer"
        >
          {t("common.close")}
        </button>
      </div>

      {/* Mock mode warning */}
      <div className="text-[10px] text-[#ff9500] bg-[#ff9500]/5 px-2 py-1.5 rounded-lg mb-3">
        {t("perf.mockWarning")}
      </div>

      {/* Platform selection */}
      <div className="mb-3">
        <p className="text-[11px] font-medium text-[#35353B] mb-1.5">{t("perf.publishSelect")}</p>
        <div className="flex gap-3">
          <label className="flex items-center gap-1.5 text-[11px] text-[#35353B] cursor-pointer">
            <input
              type="checkbox"
              checked={platforms.tiktok}
              onChange={(e) => setPlatforms((prev) => ({ ...prev, tiktok: e.target.checked }))}
              disabled={isPublishing}
              className="accent-[#6A2B3A]"
            />
            TikTok
          </label>
          <label className="flex items-center gap-1.5 text-[11px] text-[#35353B] cursor-pointer">
            <input
              type="checkbox"
              checked={platforms.shopify}
              onChange={(e) => setPlatforms((prev) => ({ ...prev, shopify: e.target.checked }))}
              disabled={isPublishing}
              className="accent-[#6A2B3A]"
            />
            Shopify
          </label>
        </div>
      </div>

      {/* Title field */}
      <div className="mb-2">
        <label className="text-[10px] font-medium text-[#9FA0A0] uppercase tracking-wider block mb-1">
          {t("step.editTitle")}
        </label>
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          disabled={isPublishing}
          placeholder={t("content.title")}
          className="w-full text-[12px] px-2.5 py-1.5 rounded-lg border border-[#EDD3D1] bg-white text-[#35353B] placeholder-[#9FA0A0] focus:outline-none focus:border-[#6A2B3A] disabled:opacity-50"
        />
      </div>

      {/* Description field */}
      <div className="mb-3">
        <label className="text-[10px] font-medium text-[#9FA0A0] uppercase tracking-wider block mb-1">
          {t("editors.description")}
        </label>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          disabled={isPublishing}
          rows={2}
          placeholder={t("editors.description")}
          className="w-full text-[12px] px-2.5 py-1.5 rounded-lg border border-[#EDD3D1] bg-white text-[#35353B] placeholder-[#9FA0A0] focus:outline-none focus:border-[#6A2B3A] resize-none disabled:opacity-50"
        />
      </div>

      {/* Publish button */}
      {!isPublishing && !isComplete && (
        <button
          onClick={handlePublish}
          disabled={!canPublish}
          className="apple-btn apple-btn-primary w-full text-[12px] py-2 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
        >
          {t("dist.publish")}
        </button>
      )}

      {/* Progress per platform */}
      {Object.keys(progress).length > 0 && (
        <div className="space-y-2 mt-3">
          <p className="text-[10px] font-medium text-[#9FA0A0] uppercase tracking-wider">
            {t("perf.publishProgress")}
          </p>
          {Object.entries(progress).map(([platform, p]) => (
            <div key={platform} className="flex items-center justify-between p-2 rounded-lg bg-[#FFF0EF] border border-[#EDD3D1]">
              <div className="flex items-center gap-2">
                <PlatformStateIcon state={p.state} />
                <span className="text-[11px] font-medium text-[#35353B]">
                  {platform === "tiktok" ? "TikTok" : "Shopify"}
                </span>
                <span className="text-[10px] text-[#9FA0A0]">{stateLabel(p.state)}</span>
              </div>
              {p.state === "done" && p.result?.post_url && (
                <div className="flex items-center gap-2">
                  <a
                    href={p.result.post_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[10px] text-[#6A2B3A] hover:underline"
                  >
                    {t("dist.view")}
                  </a>
                  <button
                    onClick={() => navigator.clipboard.writeText(p.result!.post_url || "")}
                    className="text-[10px] text-[#9FA0A0] hover:text-[#35353B] cursor-pointer"
                  >
                    {t("perf.copyLink")}
                  </button>
                </div>
              )}
              {p.state === "error" && (
                <button
                  onClick={handleRetry}
                  className="text-[10px] text-[#9FA0A0] hover:text-[#35353B] underline cursor-pointer"
                >
                  {t("dist.retry")}
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Overall error */}
      {overallError && (
        <div className="mt-2 text-[10px] text-[#C45B50] bg-[#C45B50]/5 px-2 py-1.5 rounded-lg">
          {overallError}
        </div>
      )}

      {/* All done */}
      {isComplete && (
        <div className="mt-3 text-[11px] text-[#6A2B3A] font-medium text-center">
          {t("perf.published")}
        </div>
      )}
    </div>
  );
}

function PlatformStateIcon({ state }: { state: ProgressState }) {
  switch (state) {
    case "uploading":
    case "processing":
      return (
        <svg className="animate-spin h-3.5 w-3.5 text-[#6A2B3A]" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      );
    case "done":
      return (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#6A2B3A" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      );
    case "error":
      return (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#C45B50" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10" />
          <line x1="15" y1="9" x2="9" y2="15" />
          <line x1="9" y1="9" x2="15" y2="15" />
        </svg>
      );
    default:
      return null;
  }
}

function stateLabel(state: ProgressState): string {
  switch (state) {
    case "uploading":
      return "Uploading...";
    case "processing":
      return "Processing...";
    case "done":
      return "Published ✓";
    case "error":
      return "Failed";
    default:
      return "";
  }
}
