"use client";

import { useState, useEffect } from "react";
import { fetchDistribution, fetchOutput, downloadJson, publishContent, fetchPublishStatus } from "./api";
import React from "react";
import { ShoppingBag, ShoppingCart, MusicNotes, ChatCircle, ArrowSquareOut, VideoCamera } from "@phosphor-icons/react";
import type { IconProps } from "@phosphor-icons/react";
import { useI18n } from "@/i18n/I18nProvider";

import { errorMessage } from "@/lib/errors";
const PLATFORM_ICON_MAP: Record<string, React.ComponentType<IconProps>> = {
  shopify: ShoppingBag,
  amazon: ShoppingCart,
  tiktok: MusicNotes,
  reddit: ChatCircle,
  facebook: ArrowSquareOut,
  youtube_shorts: VideoCamera,
};

interface Props {
  threadId: string;
  onRestart: () => void;
}

export default function DistributionView({ threadId, onRestart }: Props) {
  const [plans, setPlans] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedBrief, setExpandedBrief] = useState<string | null>(null);
  const [showRaw, setShowRaw] = useState(false);
  const { t, locale } = useI18n();
  const [publishResults, setPublishResults] = useState<Record<string, any>>({});
  const [publishing, setPublishing] = useState<Record<string, boolean>>({});
  const [statusPopup, setStatusPopup] = useState<{ platform: string; postId: string } | null>(null);
  const [statusData, setStatusData] = useState<any>(null);
  const [statusLoading, setStatusLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchDistribution(threadId).then((data) => {
      if (!cancelled) {
        setPlans(data.distribution_plans || []);
        setLoading(false);
      }
    }).catch(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, [threadId]);

  // Group plans by brief_id
  const groups: Record<string, any[]> = {};
  for (const plan of plans) {
    const bid = plan.brief_id || "unknown";
    if (!groups[bid]) groups[bid] = [];
    groups[bid].push(plan);
  }

  const handleDownload = async () => {
    try {
      const data = await fetchOutput(threadId);
      downloadJson(data, `pipeline-output-${threadId}.json`);
    } catch {
      // Fallback: download distribution plans
      downloadJson({ distribution_plans: plans }, `pipeline-output-${threadId}.json`);
    }
  };

  const handlePublish = async (plan: any, platform: string) => {
    const key = `${plan.script_id || plan.brief_id}-${platform}`;
    setPublishing((prev) => ({ ...prev, [key]: true }));
    try {
      const brief = plans.find((p) => p.brief_id === plan.brief_id) || plan;
      const content = {
        title: plan.title || brief.title || "",
        description: plan.caption || plan.description || "",
        video_url: plan.video_url || "",
        tags: plan.tags || [],
        thumbnail_url: plan.thumbnail_url || "",
      };
      const result = await publishContent(platform, content);
      setPublishResults((prev) => ({ ...prev, [key]: { success: true, ...result } }));
    } catch (err: unknown) {
      setPublishResults((prev) => ({ ...prev, [key]: { success: false, error: errorMessage(err, t("dist.publishFailed")) } }));
    } finally {
      setPublishing((prev) => ({ ...prev, [key]: false }));
    }
  };

  const handleCheckStatus = async (platform: string, postId: string) => {
    setStatusPopup({ platform, postId });
    setStatusLoading(true);
    setStatusData(null);
    try {
      const data = await fetchPublishStatus(platform, postId);
      setStatusData(data);
    } catch (err: unknown) {
      setStatusData({ error: errorMessage(err, t("dist.statusFailed")) });
    } finally {
      setStatusLoading(false);
    }
  };

  const getKey = (plan: any, platform: string) => `${plan.script_id || plan.brief_id}-${platform}`;

  return (
    <div className="space-y-4 animate-fade-in">
      {/* Header */}
      <div className="text-center space-y-2 py-4">
        <div className="w-14 h-14 rounded-full bg-[rgba(215,92,112,0.10)] flex items-center justify-center mx-auto">
          <svg width="26" height="26" viewBox="0 0 26 26" fill="none">
            <path d="M5 13.5L10 18.5L21 7.5" stroke="var(--fortune-red)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        <h2 className="text-xl font-semibold text-[var(--text-h1)]">{t("dist.title")}</h2>
        <p className="text-sm text-[var(--text-body)]">
          {t("dist.subtitle")}
        </p>
      </div>

      {/* Stats */}
      {!loading && plans.length > 0 && (
        <div className="grid grid-cols-3 gap-3">
          {[
            { label: t("dist.contentCount"), value: Object.keys(groups).length, color: "text-[var(--fortune-red)]" },
            { label: t("dist.versionCount"), value: plans.length, color: "text-[var(--fortune-red)]" },
            { label: t("dist.platformCount"), value: new Set(plans.flatMap((p) => (p.posts || []).map((pp: any) => pp.platform))).size, color: "text-[var(--gold-foil)]" },
          ].map((stat) => (
            <div key={stat.label} className="apple-card p-3 text-center">
              <div className={`text-xl font-bold ${stat.color}`}>{stat.value}</div>
              <div className="text-[12px] text-[var(--text-muted)] mt-0.5">{stat.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Content / Loading */}
      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="apple-card p-4">
              <div className="skeleton h-4 w-32 mb-3" />
              <div className="grid grid-cols-2 gap-2">
                <div className="skeleton h-20" />
                <div className="skeleton h-20" />
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="space-y-3">
          {Object.entries(groups).map(([briefId, briefPlans]) => {
            const exp = expandedBrief === briefId;
            return (
              <div key={briefId} className="apple-card overflow-hidden">
                <button
                  onClick={() => setExpandedBrief(exp ? null : briefId)}
                  className="w-full flex items-center gap-2 p-3 cursor-pointer text-left"
                >
                  <span className="text-xs font-mono text-[var(--text-muted)]">{briefId}</span>
                  <span className="text-xs text-[var(--text-body)]">
                    {briefPlans.length}{t("dist.platformVersions")}
                  </span>
                  <svg
                    width="12" height="12" viewBox="0 0 12 12" fill="none"
                    className={`ml-auto shrink-0 transition-transform ${exp ? "rotate-180" : ""}`}
                  >
                    <path d="M3 4.5L6 7.5L9 4.5" stroke="var(--text-muted)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </button>

                {exp && (
                  <div className="px-3 pb-3 space-y-2 animate-slide-down">
                    {briefPlans.map((plan) => (
                      <div key={plan.script_id} className="space-y-2">
                        <p className="text-[12px] font-semibold text-[var(--text-body)]">
                          {t("dist.script_id_prefix")}: {plan.script_id}
                        </p>
                        {/* Publish section */}
                        <div className="p-3 rounded-xl bg-[var(--bg-card)] border border-[rgba(215,92,112,0.18)] space-y-2">
                          <p className="text-[12px] font-semibold text-[var(--text-h1)]">{t("dist.publishToPlatform")}</p>
                          <div className="grid grid-cols-2 gap-2">
                            {(plan.posts || []).map((post: any) => {
                              const key = getKey(plan, post.platform);
                              const pub = publishResults[key];
                              const isPub = publishing[key];
                              return (
                                <div
                                  key={post.platform}
                                  className="p-3 rounded-xl bg-[var(--bg-card)] border border-[rgba(215,92,112,0.18)] space-y-1.5"
                                >
                                  <div className="flex items-center gap-1.5">
                                    {React.createElement(PLATFORM_ICON_MAP[post.platform] || ShoppingBag, { size: 16, weight: "fill", className: "text-[var(--text-body)]" })}
                                    <span className="text-xs font-semibold text-[var(--text-h1)]">
                                      {t("platform." + post.platform) || post.platform}
                                    </span>
                                  </div>
                                  {!pub && (
                                    <button
                                      onClick={() => handlePublish(plan, post.platform)}
                                      disabled={isPub}
                                      className="apple-btn apple-btn-primary text-[12px] py-1 px-2 w-full"
                                    >
                                      {isPub ? (
                                        <span className="inline-flex items-center gap-1">
                                          <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24">
                                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                                          </svg>
                                          {t("dist.publishingStatus")}
                                        </span>
                                      ) : t("dist.publish")}
                                    </button>
                                  )}
                                  {pub?.success && (
                                    <div className="space-y-1">
                                      <span className="text-[12px] px-1.5 py-0.5 rounded bg-[rgba(215,92,112,0.10)] text-[var(--fortune-red)] font-medium">
                                        {t("dist.publishedStatus")}
                                      </span>
                                      {pub.url && (
                                        <a
                                          href={pub.url}
                                          target="_blank"
                                          rel="noopener noreferrer"
                                          className="block text-[12px] text-[var(--fortune-red)] hover:underline truncate"
                                        >
                                          {pub.url}
                                        </a>
                                      )}
                                      <button
                                        onClick={() => handleCheckStatus(post.platform, pub.post_id)}
                                        className="text-[12px] text-[var(--text-body)] hover:text-[var(--text-h1)] underline cursor-pointer"
                                      >
                                        {t("dist.viewStatus")}
                                      </button>
                                    </div>
                                  )}
                                  {pub && !pub.success && (
                                    <div className="space-y-1">
                                      <span className="text-[12px] px-1.5 py-0.5 rounded bg-[rgba(196,91,80,0.10)] text-[var(--crimson-mist)] font-medium">
                                        {t("dist.failedStatus")}
                                      </span>
                                      <p className="text-[12px] text-[var(--crimson-mist)]">{pub.error}</p>
                                      <button
                                        onClick={() => handlePublish(plan, post.platform)}
                                        disabled={isPub}
                                        className="apple-btn apple-btn-primary text-[12px] py-1 px-2 w-full"
                                      >
                                        {isPub ? t("dist.retryingStatus") : t("dist.retry")}
                                      </button>
                                    </div>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        </div>
                        {/* Existing posts display */}
                        <div className="grid grid-cols-2 gap-2">
                          {(plan.posts || []).map((post: any) => (
                            <div
                              key={post.platform}
                              className="p-3 rounded-xl bg-[var(--bg-panel)] border border-[rgba(215,92,112,0.18)] space-y-1.5"
                            >
                              <div className="flex items-center gap-1.5">
                                {React.createElement(PLATFORM_ICON_MAP[post.platform] || ShoppingBag, { size: 16, weight: "fill", className: "text-[var(--text-body)]" })}
                                <span className="text-xs font-semibold text-[var(--text-h1)]">
                                  {t("platform." + post.platform) || post.platform}
                                </span>
                              </div>
                              <div className="flex flex-wrap gap-1">
                                <span className="text-[12px] px-1.5 py-0.5 rounded bg-[rgba(215,92,112,0.10)] text-[var(--fortune-red)] font-medium">
                                  {t("cta." + post.cta_type) || post.cta_type}
                                </span>
                                <span className="text-[12px] px-1.5 py-0.5 rounded bg-[rgba(89,88,94,0.10)] text-[var(--text-body)] font-medium">
                                  {t("format." + post.video_format) || post.video_format}
                                </span>
                              </div>
                              {post.product_link_placeholder && (
                                <div className="text-[12px] text-[var(--text-muted)] font-mono bg-[var(--bg-card)] rounded px-1.5 py-1 border border-[rgba(215,92,112,0.18)] truncate">
                                  {post.product_link_placeholder}
                                </div>
                              )}
                              {post.post_body && (
                                <p className="text-[12px] text-[var(--text-body)] line-clamp-3 leading-relaxed">
                                  {post.post_body}
                                </p>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-3">
        <button onClick={handleDownload} className="apple-btn apple-btn-primary flex-1">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M7 2v7M4 6l3 3 3-3" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M2 10v1.5A1.5 1.5 0 003.5 13h7a1.5 1.5 0 001.5-1.5V10" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
          {t("dist.downloadJSON")}
        </button>
        <button onClick={onRestart} className="apple-btn apple-btn-secondary">
          {t("dist.restart")}
        </button>
      </div>

      {/* Toggle raw data */}
      <button
        onClick={() => setShowRaw(!showRaw)}
        className="text-xs text-[var(--text-muted)] hover:text-[var(--text-h1)] transition-colors cursor-pointer"
      >
        {showRaw ? t("dist.hide") : t("dist.view")}{t("dist.rawData")}
      </button>
      {showRaw && (
        <pre className="p-4 rounded-xl bg-[var(--bg-panel)] text-[12px] overflow-auto max-h-96 border border-[rgba(215,92,112,0.18)]">
          {JSON.stringify(plans, null, 2)}
        </pre>
      )}

      {/* Status popup */}
      {statusPopup && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm" onClick={() => setStatusPopup(null)}>
          <div className="apple-card p-4 w-80 max-w-[90vw]" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <p className="text-sm font-semibold text-[var(--text-h1)]">{t("dist.publishStatusPopupTitle")}</p>
              <button onClick={() => setStatusPopup(null)} className="text-[var(--text-muted)] hover:text-[var(--text-h1)] cursor-pointer">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>
            {statusLoading ? (
              <div className="flex items-center justify-center py-6">
                <svg className="animate-spin h-5 w-5 text-[var(--fortune-red)]" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
              </div>
            ) : statusData?.error ? (
              <p className="text-xs text-[var(--crimson-mist)]">{statusData.error}</p>
            ) : (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[12px] text-[var(--text-body)]">{t("dist.platformLabel")}</span>
                  <span className="text-[12px] font-medium text-[var(--text-h1)]">{t("platform." + (statusData?.platform || "")) || statusData?.platform}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[12px] text-[var(--text-body)]">{t("dist.statusLabel")}</span>
                  <span className={`text-[12px] font-medium ${statusData?.status === 'published' ? 'text-[var(--fortune-red)]' : 'text-[var(--gold-foil)]'}`}>{statusData?.status}</span>
                </div>
                {statusData?.views !== undefined && (
                  <div className="flex items-center justify-between">
                    <span className="text-[12px] text-[var(--text-body)]">{t("dist.viewsLabel")}</span>
                    <span className="text-[12px] font-medium text-[var(--text-h1)]">{statusData.views}</span>
                  </div>
                )}
                {statusData?.likes !== undefined && (
                  <div className="flex items-center justify-between">
                    <span className="text-[12px] text-[var(--text-body)]">{t("dist.likesLabel")}</span>
                    <span className="text-[12px] font-medium text-[var(--text-h1)]">{statusData.likes}</span>
                  </div>
                )}
                {statusData?.sales !== undefined && (
                  <div className="flex items-center justify-between">
                    <span className="text-[12px] text-[var(--text-body)]">{t("dist.salesLabel")}</span>
                    <span className="text-[12px] font-medium text-[var(--text-h1)]">{statusData.sales}</span>
                  </div>
                )}
                {statusData?.published_at && (
                  <div className="flex items-center justify-between">
                    <span className="text-[12px] text-[var(--text-body)]">{t("dist.publishTimeLabel")}</span>
                    <span className="text-[12px] font-medium text-[var(--text-h1)]">{new Date(statusData.published_at).toLocaleString(locale === "zh" ? "zh-CN" : "en-US")}</span>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
