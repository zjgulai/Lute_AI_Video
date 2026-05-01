"use client";

import React, { useState, useMemo } from "react";
import { useI18n } from "@/i18n/I18nProvider";
import { TrendUp, TrendDown, Minus, Lightbulb, ChartBar, CaretDown, CaretUp } from "@phosphor-icons/react";
import PerformanceDashboard from "./PerformanceDashboard";

interface Props {
  result: any;
  scenario: string;
}

// Video type → primary metrics mapping
const VIDEO_TYPE_METRICS: Record<string, { primary: string[]; secondary: string[] }> = {
  brand_image: { primary: ["watchRate", "followerGrowth"], secondary: ["views", "likes", "shares"] },
  product_seed: { primary: ["ctr", "cvr", "sales"], secondary: ["views", "watchRate"] },
  unbox_review: { primary: ["watchRate", "ctr", "cvr"], secondary: ["views", "likes"] },
  comparison: { primary: ["ctr", "cvr", "sales"], secondary: ["views", "watchRate"] },
  event_promo: { primary: ["views", "shares", "ctr"], secondary: ["watchRate", "likes"] },
  product_explain: { primary: ["watchRate", "ctr"], secondary: ["views", "likes"] },
  usp_demo: { primary: ["watchRate", "ctr", "cvr"], secondary: ["views", "likes"] },
  influencer_sales: { primary: ["sales", "cvr", "ctr"], secondary: ["views", "watchRate"] },
  ugc_mix: { primary: ["views", "shares", "watchRate"], secondary: ["likes", "ctr"] },
  store_live: { primary: ["watchRate", "ctr", "cvr"], secondary: ["views", "likes"] },
  user_ugc: { primary: ["views", "watchRate", "likes"], secondary: ["shares", "ctr"] },
  // Fallback
  default: { primary: ["watchRate", "views", "likes"], secondary: ["shares", "ctr"] },
};

// Mock benchmark data for comparison
const BENCHMARKS: Record<string, number> = {
  watchRate: 0.35,
  followerGrowth: 0.08,
  ctr: 0.045,
  cvr: 0.025,
  sales: 120,
  views: 5000,
  likes: 350,
  shares: 80,
};

// Generate deterministic mock metrics from result data
function deriveMetrics(result: any): Record<string, number> {
  const audit = result?.audit_report;
  const score = audit?.overall_score || 0.7;
  const briefs = result?.briefs || [];
  const script = result?.scripts?.[0] || {};
  const duration = result?.video_duration || 30;

  // Seed from content hash for determinism
  const seed = JSON.stringify({
    product: script.product_name || briefs[0]?.product_name || "",
    platform: briefs[0]?.platform || "tiktok",
    duration,
  });
  const hash = seed.split("").reduce((acc, c) => acc + c.charCodeAt(0), 0);
  const jitter = (n: number) => n * (0.85 + ((hash % 30) / 100));

  return {
    watchRate: jitter(Math.min(0.85, score * 0.9 + 0.15)),
    followerGrowth: jitter(score * 0.12),
    ctr: jitter(score * 0.065),
    cvr: jitter(score * 0.035),
    sales: Math.round(jitter(score * 180)),
    views: Math.round(jitter(score * 8500)),
    likes: Math.round(jitter(score * 600)),
    shares: Math.round(jitter(score * 150)),
  };
}

function getVideoType(result: any): string {
  const briefs = result?.briefs || [];
  const videoType = briefs[0]?.video_type || result?.video_type;
  if (videoType) return videoType;

  // Infer from scenario + content
  const scenario = result?.scenario || "";
  if (scenario.includes("brand")) return "brand_image";
  if (scenario.includes("product")) return "product_seed";
  if (scenario.includes("live")) return "store_live";
  if (scenario.includes("influencer")) return "influencer_sales";
  return "default";
}

function formatMetric(key: string, value: number): string {
  if (["watchRate", "followerGrowth", "ctr", "cvr"].includes(key)) {
    return `${(value * 100).toFixed(1)}%`;
  }
  if (value >= 10000) return `${(value / 1000).toFixed(0)}K`;
  if (value >= 1000) return `${(value / 1000).toFixed(1)}K`;
  return value.toFixed(0);
}

function compareMetric(key: string, value: number): { delta: number; direction: "up" | "down" | "flat" } {
  const benchmark = BENCHMARKS[key] || value * 0.9;
  const delta = ((value - benchmark) / benchmark) * 100;
  if (delta > 5) return { delta, direction: "up" };
  if (delta < -5) return { delta, direction: "down" };
  return { delta, direction: "flat" };
}

export default function InsightReport({ result, scenario }: Props) {
  const { t } = useI18n();
  const [showDetail, setShowDetail] = useState(false);

  const videoType = getVideoType(result);
  const metricConfig = VIDEO_TYPE_METRICS[videoType] || VIDEO_TYPE_METRICS.default;
  const metrics = deriveMetrics(result);

  // AI summary generation
  const aiSummary = useMemo(() => {
    const primaryMetrics = metricConfig.primary;
    const bestMetric = primaryMetrics.reduce((best, key) =>
      metrics[key] > (metrics[best] || 0) ? key : best,
      primaryMetrics[0]
    );
    const bestValue = metrics[bestMetric];
    const { delta, direction } = compareMetric(bestMetric, bestValue);

    const metricName = t(`insight.${bestMetric}`);
    const comparison = direction === "up"
      ? `高于同类均值 ${delta.toFixed(0)}%`
      : direction === "down"
      ? `低于同类均值 ${Math.abs(delta).toFixed(0)}%`
      : "与同类均值持平";

    const videoTypeName = t(`videoType.${videoType}`) || t("insight.title");
    return `这条${videoTypeName}的${metricName}表现${comparison}，整体内容质量${result?.audit_report?.overall_status === "PASS" ? "达标" : "有优化空间"}。建议继续强化${metricConfig.primary[0]}相关的内容策略。`;
  }, [metrics, metricConfig, videoType, t, result]);

  // Next step suggestions
  const nextSteps = useMemo(() => {
    const steps: string[] = [];
    const { direction: ctrDir } = compareMetric("ctr", metrics.ctr);
    const { direction: watchDir } = compareMetric("watchRate", metrics.watchRate);

    if (watchDir === "down") steps.push("前3秒 Hook 吸引力不足，建议强化开头冲突或悬念");
    if (ctrDir === "down") steps.push("封面/标题点击率偏低，尝试 A/B 测试不同封面文案");
    if (metrics.shares < 100) steps.push("分享率较低，可增加互动引导或情绪共鸣点");
    if (steps.length === 0) steps.push("整体表现良好，建议扩大投放预算测试更多平台");

    return steps;
  }, [metrics]);

  // ROI breakdown (sales-type videos only)
  const showRoiTree = metricConfig.primary.includes("sales");

  return (
    <div className="space-y-4">
      {/* AI Summary */}
      <div className="apple-card p-4 border-l-4 border-l-[var(--color-accent)]">
        <div className="flex items-center gap-2 mb-2">
          <Lightbulb size={14} weight="fill" className="text-[var(--color-accent)]" />
          <span className="text-xs font-semibold text-[var(--color-text-primary)]">{t("insight.aiSummary")}</span>
        </div>
        <p className="text-sm text-[var(--color-text-secondary)] leading-relaxed">{aiSummary}</p>
      </div>

      {/* Primary Metrics */}
      <div className="grid grid-cols-3 gap-3">
        {metricConfig.primary.map((key) => {
          const value = metrics[key];
          const { delta, direction } = compareMetric(key, value);
          const Icon = direction === "up" ? TrendUp : direction === "down" ? TrendDown : Minus;
          const color = direction === "up" ? "text-[var(--jade-accent)]" : direction === "down" ? "text-[var(--color-warning)]" : "text-[var(--color-text-tertiary)]";

          return (
            <div key={key} className="apple-card p-3 text-center">
              <div className="text-[10px] text-[var(--color-text-tertiary)] uppercase tracking-wider mb-1">
                {t(`insight.${key}`)}
              </div>
              <div className="text-lg font-bold text-[var(--color-text-primary)]">
                {formatMetric(key, value)}
              </div>
              <div className={`flex items-center justify-center gap-0.5 text-[10px] font-medium ${color} mt-0.5`}>
                <Icon size={10} weight="fill" />
                {direction === "up" ? "+" : direction === "down" ? "" : ""}{delta.toFixed(0)}%
              </div>
            </div>
          );
        })}
      </div>

      {/* Secondary Metrics */}
      <div className="apple-card p-3">
        <div className="text-[10px] font-medium text-[var(--color-text-tertiary)] uppercase tracking-wider mb-2">
          {t("insight.comparison")}
        </div>
        <div className="space-y-2">
          {metricConfig.secondary.map((key) => {
            const value = metrics[key];
            const benchmark = BENCHMARKS[key] || value * 0.9;
            const pct = Math.min(100, (value / (benchmark * 1.5)) * 100);

            return (
              <div key={key} className="flex items-center gap-3">
                <span className="text-xs text-[var(--color-text-secondary)] w-16 shrink-0">{t(`insight.${key}`)}</span>
                <div className="flex-1 h-2 bg-[var(--color-bg-secondary)] rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full bg-[var(--color-accent)]/60 transition-all duration-500"
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <span className="text-xs text-[var(--color-text-primary)] font-medium w-14 text-right">
                  {formatMetric(key, value)}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* ROI Breakdown Tree (sales-type only) */}
      {showRoiTree && (
        <div className="apple-card p-4">
          <div className="flex items-center gap-2 mb-3">
            <ChartBar size={14} weight="fill" className="text-[var(--color-accent)]" />
            <span className="text-xs font-semibold text-[var(--color-text-primary)]">{t("insight.roiTree")}</span>
          </div>
          <div className="space-y-2 text-xs">
            <RoiNode label={`${t("insight.views")}: ${formatMetric("views", metrics.views)}`} level={0} />
            <RoiNode label={`${t("insight.ctr")}: ${formatMetric("ctr", metrics.ctr)} → ${formatMetric("views", metrics.views * metrics.ctr)} 点击`} level={1} />
            <RoiNode label={`${t("insight.cvr")}: ${formatMetric("cvr", metrics.cvr)} → ${formatMetric("sales", metrics.sales)} ${t("insight.sales")}`} level={2} />
            <div className="pl-8 pt-1 border-t border-[var(--color-border-light)] mt-2">
              <span className="text-[var(--color-text-secondary)]">
                预估 ROI: <span className="font-bold text-[var(--jade-accent)]">{((metrics.sales * 50) / 500).toFixed(1)}x</span>
                <span className="text-[var(--color-text-tertiary)] ml-1">(按客单价 $50, 投放成本 $500)</span>
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Next Steps */}
      <div className="apple-card p-4">
        <div className="flex items-center gap-2 mb-2">
          <Lightbulb size={14} weight="fill" className="text-[var(--jade-accent)]" />
          <span className="text-xs font-semibold text-[var(--color-text-primary)]">{t("insight.nextStep")}</span>
        </div>
        <ul className="space-y-1.5">
          {nextSteps.map((step, i) => (
            <li key={i} className="text-xs text-[var(--color-text-secondary)] flex items-start gap-2">
              <span className="text-[var(--color-accent)] shrink-0">{i + 1}.</span>
              {step}
            </li>
          ))}
        </ul>
      </div>

      {/* Expandable: Detailed Performance Dashboard */}
      <div className="border border-[var(--color-border-light)] rounded-xl overflow-hidden">
        <button
          onClick={() => setShowDetail(!showDetail)}
          className="flex items-center justify-between w-full px-4 py-3 text-left hover:bg-[var(--color-bg-secondary)]/50 transition-colors"
        >
          <span className="text-xs font-medium text-[var(--color-text-secondary)]">{t("insight.detailData")}</span>
          {showDetail ? <CaretUp size={14} weight="fill" className="text-[var(--color-text-tertiary)]" /> : <CaretDown size={14} weight="fill" className="text-[var(--color-text-tertiary)]" />}
        </button>
        {showDetail && (
          <div className="px-4 pb-4 animate-fade-in">
            <PerformanceDashboard scenario={scenario} />
          </div>
        )}
      </div>
    </div>
  );
}

function RoiNode({ label, level }: { label: string; level: number }) {
  return (
    <div className="flex items-center gap-2" style={{ paddingLeft: level * 20 }}>
      <div className="w-1.5 h-1.5 rounded-full bg-[var(--color-accent)]/40" />
      <span className="text-[var(--color-text-secondary)]">{label}</span>
    </div>
  );
}
