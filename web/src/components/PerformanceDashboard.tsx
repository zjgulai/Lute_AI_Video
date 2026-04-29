"use client";

import { useState, useEffect, useCallback } from "react";
import { useI18n } from "@/i18n/I18nProvider";
import { fetchDashboardOverview } from "./api";

interface Props {
  scenario?: string;
  onClose?: () => void;
}

interface VideoRow {
  video_id: string;
  title: string;
  scenario: string;
  platform: string;
  ctr: number;
  cvr: number;
  watch_rate: number;
  followers_gained: number;
  sales: number;
  views: number;
  history?: { pulled_at: string; ctr: number; watch_rate: number }[];
}

interface ScenarioCard {
  scenario: string;
  avg_watch_rate: number;
  avg_ctr: number;
  avg_cvr: number;
  total_videos: number;
  total_sales: number;
}

interface PlatformComparison {
  platform: string;
  avg_ctr: number;
  avg_cvr: number;
  avg_watch_rate: number;
  total_views: number;
  scenario_breakdown: Record<string, { avg_ctr: number; avg_cvr: number; avg_watch_rate: number }>;
}

interface DashboardData {
  videos: VideoRow[];
  scenarios: ScenarioCard[];
  platforms: PlatformComparison[];
}

type ViewTab = "list" | "scenario" | "platform";

const SCENARIO_OPTIONS = ["All", "S1", "S2", "S3"] as const;

export default function PerformanceDashboard({ scenario: initialScenario, onClose }: Props) {
  const { t } = useI18n();
  const [viewTab, setViewTab] = useState<ViewTab>("list");
  const [scenarioFilter, setScenarioFilter] = useState(initialScenario || "All");
  const [platformFilter, setPlatformFilter] = useState("All");
  const [timeFilter, setTimeFilter] = useState("30d");
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const scenario = scenarioFilter === "All" ? undefined : scenarioFilter;
      const platform = platformFilter === "All" ? undefined : platformFilter;
      const days = timeFilter === "7d" ? 7 : timeFilter === "14d" ? 14 : 30;
      const result = await fetchDashboardOverview(scenario, platform, days);
      setData(result);
    } catch (err: any) {
      setError(err.message || t("common.fetchFailed"));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [scenarioFilter, platformFilter, timeFilter, t]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const timeOptions = [
    { value: "7d", label: t("perf.filter7d") },
    { value: "14d", label: t("perf.filter14d") },
    { value: "30d", label: t("perf.filter30d") },
  ];

  const viewTabs: { id: ViewTab; label: string }[] = [
    { id: "list", label: t("perf.viewList") },
    { id: "scenario", label: t("perf.viewScenario") },
    { id: "platform", label: t("perf.viewPlatform") },
  ];

  if (loading) {
    return (
      <div className="space-y-3 animate-pulse">
        <div className="h-8 bg-[#f5f5f7] rounded-lg w-2/3" />
        <div className="h-10 bg-[#f5f5f7] rounded-lg" />
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-16 bg-[#f5f5f7] rounded-lg" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-10">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#ff453a" strokeWidth="1.5" className="mx-auto mb-2">
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="8" x2="12" y2="12" />
          <line x1="12" y1="16" x2="12.01" y2="16" />
        </svg>
        <p className="text-xs text-[#ff453a]">{error}</p>
      </div>
    );
  }

  const hasVideoData = data?.videos && data.videos.length > 0;

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-[#1d1d1f]">{t("perf.title")}</h3>
        {onClose && (
          <button onClick={onClose} className="text-[10px] text-[#86868b] hover:text-[#1d1d1f] cursor-pointer">
            {t("common.close")}
          </button>
        )}
      </div>

      {/* View tabs */}
      <div className="flex border-b border-[#e8e8ed]">
        {viewTabs.map((vt) => (
          <button
            key={vt.id}
            onClick={() => setViewTab(vt.id)}
            className={`px-3 py-2 text-[11px] font-medium border-b-2 transition-colors cursor-pointer ${
              viewTab === vt.id
                ? "border-[#7CB342] text-[#7CB342]"
                : "border-transparent text-[#86868b] hover:text-[#1d1d1f]"
            }`}
          >
            {vt.label}
          </button>
        ))}
      </div>

      {/* Filters (for list view and platform view) */}
      {viewTab !== "scenario" && (
        <div className="flex gap-2 flex-wrap">
          <select
            value={scenarioFilter}
            onChange={(e) => setScenarioFilter(e.target.value)}
            className="text-[11px] px-2 py-1 rounded-lg border border-[#e8e8ed] bg-white text-[#1d1d1f] cursor-pointer"
          >
            {SCENARIO_OPTIONS.map((s) => (
              <option key={s} value={s}>{s === "All" ? t("perf.filterAll") : s}</option>
            ))}
          </select>
          <select
            value={platformFilter}
            onChange={(e) => setPlatformFilter(e.target.value)}
            className="text-[11px] px-2 py-1 rounded-lg border border-[#e8e8ed] bg-white text-[#1d1d1f] cursor-pointer"
          >
            <option value="All">{t("perf.filterAll")}</option>
            <option value="tiktok">TikTok</option>
            <option value="shopify">Shopify</option>
          </select>
          <div className="flex gap-1">
            {timeOptions.map((opt) => (
              <button
                key={opt.value}
                onClick={() => setTimeFilter(opt.value)}
                className={`text-[10px] px-2 py-1 rounded-lg border cursor-pointer ${
                  timeFilter === opt.value
                    ? "bg-[#7CB342] text-white border-[#7CB342]"
                    : "bg-white text-[#86868b] border-[#e8e8ed] hover:border-[#86868b]"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* No data state */}
      {!hasVideoData && (
        <div className="text-center py-10">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#e8e8ed" strokeWidth="1.5" className="mx-auto mb-2">
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <path d="M3 9h18" />
            <path d="M9 21V9" />
          </svg>
          <p className="text-xs text-[#aeaeb2]">{t("perf.noData")}</p>
          <p className="text-[10px] text-[#aeaeb2] mt-1">{t("perf.noDataHint")}</p>
        </div>
      )}

      {/* View 1: Video Performance List */}
      {viewTab === "list" && hasVideoData && <VideoListView videos={data!.videos} />}

      {/* View 2: Scenario Aggregation */}
      {viewTab === "scenario" && (
        <ScenarioView
          scenarios={data?.scenarios || []}
          onScenarioClick={(s) => { setScenarioFilter(s); setViewTab("list"); }}
        />
      )}

      {/* View 3: Platform Comparison */}
      {viewTab === "platform" && hasVideoData && <PlatformView platforms={data!.platforms || []} />}
    </div>
  );
}

// ── View 1: Video Performance List ──

function VideoListView({ videos }: { videos: VideoRow[] }) {
  const { t } = useI18n();
  const [expandedId, setExpandedId] = useState<string | null>(null);

  return (
    <div className="space-y-1">
      {videos.map((v) => (
        <div key={v.video_id} className="apple-card p-2 bg-white border border-[#e8e8ed]">
          <button
            onClick={() => setExpandedId(expandedId === v.video_id ? null : v.video_id)}
            className="w-full text-left cursor-pointer"
          >
            <div className="flex items-center gap-2 text-[11px]">
              <span className="flex-1 font-medium text-[#1d1d1f] truncate">{v.title}</span>
              <ScenarioBadge scenario={v.scenario} />
              <PlatformBadge platform={v.platform} />
              <MetricCell value={v.ctr} format="pct" />
              <MetricCell value={v.cvr} format="pct" />
              <MetricCell value={v.watch_rate} format="pct" />
              <MetricCell value={v.followers_gained} format="num" />
              <MetricCell value={v.sales} format="num" />
              <svg
                width="10" height="10" viewBox="0 0 10 10" fill="none"
                className={`transition-transform ${expandedId === v.video_id ? "rotate-180" : ""}`}
              >
                <path d="M2.5 3.5 L5 6.5 L7.5 3.5" stroke="#aeaeb2" strokeWidth="1.2" strokeLinecap="round" />
              </svg>
            </div>
          </button>

          {/* Expanded: mini trend chart */}
          {expandedId === v.video_id && v.history && v.history.length > 0 && (
            <div className="mt-2 pt-2 border-t border-[#e8e8ed]">
              <MiniTrendChart history={v.history} />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function ScenarioBadge({ scenario }: { scenario: string }) {
  const s = scenario.toUpperCase();
  const colorMap: Record<string, string> = {
    S1: "bg-[#007aff]/10 text-[#007aff]",
    S2: "bg-[#ff9500]/10 text-[#ff9500]",
    S3: "bg-[#5856d6]/10 text-[#5856d6]",
  };
  return (
    <span className={`text-[9px] font-semibold px-1.5 py-0.5 rounded-full shrink-0 ${colorMap[s] || "bg-[#86868b]/10 text-[#86868b]"}`}>
      {s}
    </span>
  );
}

function PlatformBadge({ platform }: { platform: string }) {
  const p = platform.toLowerCase();
  const colorMap: Record<string, string> = {
    tiktok: "bg-[#1d1d1f]/10 text-[#1d1d1f]",
    shopify: "bg-[#5e6ad2]/10 text-[#5e6ad2]",
  };
  return (
    <span className={`text-[9px] font-semibold px-1.5 py-0.5 rounded-full shrink-0 ${colorMap[p] || "bg-[#86868b]/10 text-[#86868b]"}`}>
      {p === "tiktok" ? "TT" : p === "shopify" ? "SP" : p.toUpperCase()}
    </span>
  );
}

function MetricCell({ value, format }: { value: number; format: "pct" | "num" }) {
  const display = format === "pct"
    ? (value * 100).toFixed(1) + "%"
    : String(value);

  const isHighCtr = format === "pct" && value > 0.04;
  const isLowCtr = format === "pct" && value < 0.02;

  let textClass = "text-[#86868b]";
  if (isHighCtr) textClass = "text-[#7CB342] font-semibold";
  else if (isLowCtr) textClass = "text-[#ff453a]";

  return (
    <span className={`text-[10px] tabular-nums w-10 text-right shrink-0 ${textClass}`}>
      {display}
    </span>
  );
}

function MiniTrendChart({ history }: { history: { pulled_at: string; ctr: number; watch_rate: number }[] }) {
  const { t } = useI18n();
  const points = history.slice(-10);
  const maxVal = Math.max(...points.map((p) => Math.max(p.ctr, p.watch_rate)), 0.01);
  const w = 160;
  const h = 40;

  const makePath = (key: "ctr" | "watch_rate") => {
    if (points.length < 2) return "";
    const stepX = w / (points.length - 1);
    return points
      .map((p, i) => `${i === 0 ? "M" : "L"}${i * stepX},${h - (p[key] / maxVal) * h}`)
      .join(" ");
  };

  return (
    <div className="flex items-center gap-4">
      <svg width={w} height={h} className="shrink-0">
        <path d={makePath("ctr")} fill="none" stroke="#7CB342" strokeWidth="1.5" />
        <path d={makePath("watch_rate")} fill="none" stroke="#007aff" strokeWidth="1.5" strokeDasharray="3 2" />
      </svg>
      <div className="text-[9px] text-[#aeaeb2] space-y-0.5">
        <div className="flex items-center gap-1">
          <span className="w-2 h-0.5 bg-[#7CB342]" />
          <span>CTR</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="w-2 h-0.5 bg-[#007aff]" />
          <span>{t("perf.watchRate")}</span>
        </div>
      </div>
    </div>
  );
}

// ── View 2: Scenario Aggregation ──

function ScenarioView({ scenarios, onScenarioClick }: { scenarios: ScenarioCard[]; onScenarioClick: (scenario: string) => void }) {
  const { t } = useI18n();
  if (scenarios.length === 0) {
    return (
      <div className="text-center py-10">
        <p className="text-xs text-[#aeaeb2]">{t("perf.noData")}</p>
      </div>
    );
  }

  // Find the best card (highest avg CTR)
  const bestScenario = scenarios.reduce((best, s) => (s.avg_ctr > (best?.avg_ctr || 0) ? s : best), scenarios[0]);

  return (
    <div className="grid grid-cols-3 gap-3">
      {scenarios.map((s) => {
        const isBest = s.scenario === bestScenario.scenario;
        return (
          <button
            key={s.scenario}
            onClick={() => onScenarioClick(s.scenario)}
            className={`apple-card p-4 text-left cursor-pointer transition-all hover:shadow-md ${
              isBest ? "bg-[#7CB342]/5 border-[#7CB342]/20 border" : "bg-white border border-[#e8e8ed]"
            }`}
          >
            <p className="text-[13px] font-bold text-[#1d1d1f] mb-3">{s.scenario}</p>
            <div className="space-y-2 text-[11px]">
              <div className="flex justify-between">
                <span className="text-[#86868b]">{t("perf.avgWatchRate")}</span>
                <span className="font-medium text-[#1d1d1f]">{(s.avg_watch_rate * 100).toFixed(1)}%</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#86868b]">{t("perf.avgCtr")}</span>
                <span className="font-medium text-[#1d1d1f]">{(s.avg_ctr * 100).toFixed(1)}%</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#86868b]">{t("perf.avgCvr")}</span>
                <span className="font-medium text-[#1d1d1f]">{(s.avg_cvr * 100).toFixed(1)}%</span>
              </div>
              <div className="border-t border-[#e8e8ed] pt-2 mt-2">
                <div className="flex justify-between">
                  <span className="text-[#86868b]">{t("perf.totalVideos")}</span>
                  <span className="font-medium text-[#1d1d1f]">{s.total_videos}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[#86868b]">{t("perf.totalSales")}</span>
                  <span className="font-medium text-[#1d1d1f]">{s.total_sales}</span>
                </div>
              </div>
            </div>
          </button>
        );
      })}
    </div>
  );
}

// ── View 3: Platform Comparison ──

function PlatformView({ platforms }: { platforms: PlatformComparison[] }) {
  const { t } = useI18n();

  if (platforms.length === 0) {
    return (
      <div className="text-center py-10">
        <p className="text-xs text-[#aeaeb2]">{t("perf.noData")}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {platforms.map((p) => (
        <div key={p.platform} className="apple-card p-3 bg-white border border-[#e8e8ed]">
          <p className="text-[12px] font-semibold text-[#1d1d1f] mb-2">
            {p.platform === "tiktok" ? "TikTok" : p.platform === "shopify" ? "Shopify" : p.platform}
          </p>

          {/* Overall metrics */}
          <div className="grid grid-cols-4 gap-2 mb-3 text-[11px]">
            <div>
              <p className="text-[#86868b]">{t("perf.ctr")}</p>
              <p className="font-semibold text-[#1d1d1f]">{(p.avg_ctr * 100).toFixed(1)}%</p>
            </div>
            <div>
              <p className="text-[#86868b]">{t("perf.cvr")}</p>
              <p className="font-semibold text-[#1d1d1f]">{(p.avg_cvr * 100).toFixed(1)}%</p>
            </div>
            <div>
              <p className="text-[#86868b]">{t("perf.watchRate")}</p>
              <p className="font-semibold text-[#1d1d1f]">{(p.avg_watch_rate * 100).toFixed(1)}%</p>
            </div>
            <div>
              <p className="text-[#86868b]">{t("perf.views")}</p>
              <p className="font-semibold text-[#1d1d1f]">{p.total_views}</p>
            </div>
          </div>

          {/* Scenario breakdown */}
          {p.scenario_breakdown && Object.keys(p.scenario_breakdown).length > 0 && (
            <div className="space-y-1.5">
              <p className="text-[10px] text-[#aeaeb2] uppercase tracking-wider">{t("perf.scenario")}</p>
              {Object.entries(p.scenario_breakdown).map(([scenario, metrics]) => (
                <div key={scenario} className="grid grid-cols-4 gap-2 text-[10px] pl-2 border-l-2 border-[#e8e8ed]">
                  <span className="font-medium text-[#1d1d1f]">{scenario}</span>
                  <span className="text-[#86868b]">{(metrics.avg_ctr * 100).toFixed(1)}%</span>
                  <span className="text-[#86868b]">{(metrics.avg_cvr * 100).toFixed(1)}%</span>
                  <span className="text-[#86868b]">{(metrics.avg_watch_rate * 100).toFixed(1)}%</span>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
