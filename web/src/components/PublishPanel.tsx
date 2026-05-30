"use client";

import { useState } from "react";
import { useI18n } from "@/i18n/I18nProvider";
import { publishVideo } from "./api";

import { errorMessage } from "@/lib/errors";
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
    } catch (err: unknown) {
      setOverallError(errorMessage(err, t("common.fetchFailed")));
      const errorProgress: Record<string, PlatformProgress> = {};
      selectedPlatforms.forEach((p) => {
        errorProgress[p] = { state: "error", result: { platform: p, success: false, error: errorMessage(err) } };
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

  return (
    <div className="apple-card p-4 bg-[var(--bg-card)] border border-[rgba(215,92,112,0.18)]">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-md bg-[rgba(215,92,112,0.10)] flex items-center justify-center">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--fortune-red)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="17 1 21 5 17 9" />
              <path d="M3 11V9a4 4 0 0 1 4-4h14" />
              <polyline points="7 23 3 19 7 15" />
              <path d="M21 13v2a4 4 0 0 1-4 4H3" />
            </svg>
          </div>
          <h3 className="text-sm font-semibold text-[var(--text-h1)]">{t("perf.publishTitle")}</h3>
        </div>
        <button
          onClick={handleClose}
          className="text-[12px] text-[var(--text-muted)] hover:text-[var(--text-h1)] cursor-pointer"
        >
          {t("common.close")}
        </button>
      </div>

      {/* Mock mode warning */}
      <div className="text-[12px] text-[var(--gold-foil)] bg-[rgba(255,159,10,0.05)] px-2 py-1.5 rounded-lg mb-3">
        {t("perf.mockWarning")}
      </div>

      {/* Platform selection */}
      <div className="mb-3">
        <p className="text-[12px] font-medium text-[var(--text-h1)] mb-1.5">{t("perf.publishSelect")}</p>
        <div className="flex gap-3">
          <label className="flex items-center gap-1.5 text-[12px] text-[var(--text-h1)] cursor-pointer">
            <input
              type="checkbox"
              checked={platforms.tiktok}
              onChange={(e) => setPlatforms((prev) => ({ ...prev, tiktok: e.target.checked }))}
              disabled={isPublishing}
              className="accent-[var(--fortune-red)]"
            />
            TikTok
          </label>
          <label className="flex items-center gap-1.5 text-[12px] text-[var(--text-h1)] cursor-pointer">
            <input
              type="checkbox"
              checked={platforms.shopify}
              onChange={(e) => setPlatforms((prev) => ({ ...prev, shopify: e.target.checked }))}
              disabled={isPublishing}
              className="accent-[var(--fortune-red)]"
            />
            Shopify
          </label>
        </div>
      </div>

      {/* Title field */}
      <div className="mb-2">
        <label className="text-[12px] font-medium text-[var(--text-muted)] uppercase tracking-wider block mb-1">
          {t("step.editTitle")}
        </label>
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          disabled={isPublishing}
          placeholder={t("content.title")}
          className="w-full text-[12px] px-2.5 py-1.5 rounded-lg border border-[rgba(215,92,112,0.18)] bg-[var(--bg-card)] text-[var(--text-h1)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--fortune-red)] disabled:opacity-50"
        />
      </div>

      {/* Description field */}
      <div className="mb-3">
        <label className="text-[12px] font-medium text-[var(--text-muted)] uppercase tracking-wider block mb-1">
          {t("editors.description")}
        </label>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          disabled={isPublishing}
          rows={2}
          placeholder={t("editors.description")}
          className="w-full text-[12px] px-2.5 py-1.5 rounded-lg border border-[rgba(215,92,112,0.18)] bg-[var(--bg-card)] text-[var(--text-h1)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--fortune-red)] resize-none disabled:opacity-50"
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
          <p className="text-[12px] font-medium text-[var(--text-muted)] uppercase tracking-wider">
            {t("perf.publishProgress")}
          </p>
          {Object.entries(progress).map(([platform, p]) => (
            <div key={platform} className="flex items-center justify-between p-2 rounded-lg bg-[var(--bg-card)] border border-[rgba(215,92,112,0.18)]">
              <div className="flex items-center gap-2">
                <PlatformStateIcon state={p.state} />
                <span className="text-[12px] font-medium text-[var(--text-h1)]">
                  {platform === "tiktok" ? "TikTok" : "Shopify"}
                </span>
                <span className="text-[12px] text-[var(--text-muted)]">{stateLabel(p.state)}</span>
              </div>
              {p.state === "done" && p.result?.post_url && (
                <div className="flex items-center gap-2">
                  <a
                    href={p.result.post_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[12px] text-[var(--fortune-red)] hover:underline"
                  >
                    {t("dist.view")}
                  </a>
                  <button
                    onClick={() => navigator.clipboard.writeText(p.result!.post_url || "")}
                    className="text-[12px] text-[var(--text-muted)] hover:text-[var(--text-h1)] cursor-pointer"
                  >
                    {t("perf.copyLink")}
                  </button>
                </div>
              )}
              {p.state === "error" && (
                <button
                  onClick={handleRetry}
                  className="text-[12px] text-[var(--text-muted)] hover:text-[var(--text-h1)] underline cursor-pointer"
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
        <div className="mt-2 text-[12px] text-[var(--crimson-mist)] bg-[rgba(196,91,80,0.05)] px-2 py-1.5 rounded-lg">
          {overallError}
        </div>
      )}

      {/* All done */}
      {isComplete && (
        <div className="mt-3 text-[12px] text-[var(--fortune-red)] font-medium text-center">
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
        <svg className="animate-spin h-3.5 w-3.5 text-[var(--fortune-red)]" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      );
    case "done":
      return (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--fortune-red)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      );
    case "error":
      return (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--crimson-mist)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
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
