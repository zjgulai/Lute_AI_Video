"use client";

import { useState, useEffect, useCallback } from "react";
import { useI18n } from "@/i18n/I18nProvider";
import { fetchDashboardOverview } from "./api";

import { errorMessage } from "@/lib/errors";
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
    } catch (err: unknown) {
      setError(errorMessage(err, t("common.fetchFailed")));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [scenarioFilter, platformFilter, timeFilter, t]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
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
        <div className="h-8 bg-[var(--bg-card)] rounded-lg w-2/3" />
        <div className="h-10 bg-[var(--bg-card)] rounded-lg" />
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-16 bg-[var(--bg-card)] rounded-lg" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-10">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#8C3C4B" strokeWidth="1.5" className="mx-auto mb-2">
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="8" x2="12" y2="12" />
          <line x1="12" y1="16" x2="12.01" y2="16" />
        </svg>
        <p className="text-xs text-[var(--crimson-mist)]">{error}</p>
      </div>
    );
  }

  const hasVideoData = data?.videos && data.videos.length > 0;

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-[var(--text-h1)]">{t("perf.title")}</h3>
        {onClose && (
          <button onClick={onClose} className="text-[12px] text-[var(--text-muted)] hover:text-[var(--text-h1)] cursor-pointer">
            {t("common.close")}
          </button>
        )}
      </div>

      {/* View tabs */}
      <div className="flex border-b border-[rgba(215,92,112,0.18)]">
        {viewTabs.map((vt) => (
          <button
            key={vt.id}
            onClick={() => setViewTab(vt.id)}
            className={`px-3 py-2 text-[12px] font-medium border-b-2 transition-colors cursor-pointer ${
              viewTab === vt.id
                ? "border-[var(--fortune-red)] text-[var(--fortune-red)]"
                : "border-transparent text-[var(--text-muted)] hover:text-[var(--text-h1)]"
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
            className="text-[12px] px-2 py-1 rounded-lg border border-[rgba(215,92,112,0.18)] bg-[var(--bg-card)] text-[var(--text-h1)] cursor-pointer"
          >
            {SCENARIO_OPTIONS.map((s) => (
              <option key={s} value={s}>{s === "All" ? t("perf.filterAll") : s}</option>
            ))}
          </select>
          <select
            value={platformFilter}
            onChange={(e) => setPlatformFilter(e.target.value)}
            className="text-[12px] px-2 py-1 rounded-lg border border-[rgba(215,92,112,0.18)] bg-[var(--bg-card)] text-[var(--text-h1)] cursor-pointer"
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
                className={`text-[12px] px-2 py-1 rounded-lg border cursor-pointer ${
                  timeFilter === opt.value
                    ? "bg-[var(--fortune-red)] text-white border-[var(--fortune-red)]"
                    : "bg-[var(--bg-card)] text-[var(--text-muted)] border-[rgba(215,92,112,0.18)] hover:border-[var(--text-muted)]"
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
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="rgba(215,92,112,0.18)" strokeWidth="1.5" className="mx-auto mb-2">
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <path d="M3 9h18" />
            <path d="M9 21V9" />
          </svg>
          <p className="text-xs text-[var(--text-muted)]">{t("perf.noData")}</p>
          <p className="text-[12px] text-[var(--text-muted)] mt-1">{t("perf.noDataHint")}</p>
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
        <div key={v.video_id} className="apple-card p-2 bg-[var(--bg-card)] border border-[rgba(215,92,112,0.18)]">
          <button
            onClick={() => setExpandedId(expandedId === v.video_id ? null : v.video_id)}
            className="w-full text-left cursor-pointer"
          >
            <div className="flex items-center gap-2 text-[12px]">
              <span className="flex-1 font-medium text-[var(--text-h1)] truncate">{v.title}</span>
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
                <path d="M2.5 3.5 L5 6.5 L7.5 3.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
              </svg>
            </div>
          </button>

          {/* Expanded: mini trend chart */}
          {expandedId === v.video_id && v.history && v.history.length > 0 && (
            <div className="mt-2 pt-2 border-t border-[rgba(215,92,112,0.18)]">
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
    S1: "bg-[rgba(92,141,201,0.10)] text-[var(--cinema-azure)]",
    S2: "bg-[rgba(220,190,120,0.10)] text-[var(--gold-foil)]",
    S3: "bg-[rgba(155,124,196,0.10)] text-[var(--cinema-violet)]",
  };
  return (
    <span className={`text-[12px] font-semibold px-1.5 py-0.5 rounded-full shrink-0 ${colorMap[s] || "bg-[rgba(159,160,160,0.10)] text-[var(--text-muted)]"}`}>
      {s}
    </span>
  );
}

function PlatformBadge({ platform }: { platform: string }) {
  const p = platform.toLowerCase();
  const colorMap: Record<string, string> = {
    tiktok: "bg-[rgba(53,53,59,0.10)] text-[var(--text-h1)]",
    shopify: "bg-[rgba(155,124,196,0.10)] text-[var(--cinema-violet)]",
  };
  return (
    <span className={`text-[12px] font-semibold px-1.5 py-0.5 rounded-full shrink-0 ${colorMap[p] || "bg-[rgba(159,160,160,0.10)] text-[var(--text-muted)]"}`}>
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

  let textClass = "text-[var(--text-muted)]";
  if (isHighCtr) textClass = "text-[var(--fortune-red)] font-semibold";
  else if (isLowCtr) textClass = "text-[var(--crimson-mist)]";

  return (
    <span className={`text-[12px] tabular-nums w-10 text-right shrink-0 ${textClass}`}>
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
        <path d={makePath("ctr")} fill="none" stroke="#D75C70" strokeWidth="1.5" />
        <path d={makePath("watch_rate")} fill="none" stroke="#5C8DC9" strokeWidth="1.5" strokeDasharray="3 2" />
      </svg>
      <div className="text-[12px] text-[var(--text-muted)] space-y-0.5">
        <div className="flex items-center gap-1">
          <span className="w-2 h-0.5 bg-[var(--fortune-red)]" />
          <span>CTR</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="w-2 h-0.5 bg-[var(--cinema-azure)]" />
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
        <p className="text-xs text-[var(--text-muted)]">{t("perf.noData")}</p>
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
              isBest ? "bg-[rgba(215,92,112,0.05)] border-[rgba(215,92,112,0.20)] border" : "bg-[var(--bg-card)] border border-[rgba(215,92,112,0.18)]"
            }`}
          >
            <p className="text-[13px] font-bold text-[var(--text-h1)] mb-3">{s.scenario}</p>
            <div className="space-y-2 text-[12px]">
              <div className="flex justify-between">
                <span className="text-[var(--text-muted)]">{t("perf.avgWatchRate")}</span>
                <span className="font-medium text-[var(--text-h1)]">{(s.avg_watch_rate * 100).toFixed(1)}%</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[var(--text-muted)]">{t("perf.avgCtr")}</span>
                <span className="font-medium text-[var(--text-h1)]">{(s.avg_ctr * 100).toFixed(1)}%</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[var(--text-muted)]">{t("perf.avgCvr")}</span>
                <span className="font-medium text-[var(--text-h1)]">{(s.avg_cvr * 100).toFixed(1)}%</span>
              </div>
              <div className="border-t border-[rgba(215,92,112,0.18)] pt-2 mt-2">
                <div className="flex justify-between">
                  <span className="text-[var(--text-muted)]">{t("perf.totalVideos")}</span>
                  <span className="font-medium text-[var(--text-h1)]">{s.total_videos}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[var(--text-muted)]">{t("perf.totalSales")}</span>
                  <span className="font-medium text-[var(--text-h1)]">{s.total_sales}</span>
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
        <p className="text-xs text-[var(--text-muted)]">{t("perf.noData")}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {platforms.map((p) => (
        <div key={p.platform} className="apple-card p-3 bg-[var(--bg-card)] border border-[rgba(215,92,112,0.18)]">
          <p className="text-[12px] font-semibold text-[var(--text-h1)] mb-2">
            {p.platform === "tiktok" ? "TikTok" : p.platform === "shopify" ? "Shopify" : p.platform}
          </p>

          {/* Overall metrics */}
          <div className="grid grid-cols-4 gap-2 mb-3 text-[12px]">
            <div>
              <p className="text-[var(--text-muted)]">{t("perf.ctr")}</p>
              <p className="font-semibold text-[var(--text-h1)]">{(p.avg_ctr * 100).toFixed(1)}%</p>
            </div>
            <div>
              <p className="text-[var(--text-muted)]">{t("perf.cvr")}</p>
              <p className="font-semibold text-[var(--text-h1)]">{(p.avg_cvr * 100).toFixed(1)}%</p>
            </div>
            <div>
              <p className="text-[var(--text-muted)]">{t("perf.watchRate")}</p>
              <p className="font-semibold text-[var(--text-h1)]">{(p.avg_watch_rate * 100).toFixed(1)}%</p>
            </div>
            <div>
              <p className="text-[var(--text-muted)]">{t("perf.views")}</p>
              <p className="font-semibold text-[var(--text-h1)]">{p.total_views}</p>
            </div>
          </div>

          {/* Scenario breakdown */}
          {p.scenario_breakdown && Object.keys(p.scenario_breakdown).length > 0 && (
            <div className="space-y-1.5">
              <p className="text-[12px] text-[var(--text-muted)] uppercase tracking-wider">{t("perf.scenario")}</p>
              {Object.entries(p.scenario_breakdown).map(([scenario, metrics]) => (
                <div key={scenario} className="grid grid-cols-4 gap-2 text-[12px] pl-2 border-l-2 border-[rgba(215,92,112,0.18)]">
                  <span className="font-medium text-[var(--text-h1)]">{scenario}</span>
                  <span className="text-[var(--text-muted)]">{(metrics.avg_ctr * 100).toFixed(1)}%</span>
                  <span className="text-[var(--text-muted)]">{(metrics.avg_cvr * 100).toFixed(1)}%</span>
                  <span className="text-[var(--text-muted)]">{(metrics.avg_watch_rate * 100).toFixed(1)}%</span>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
