"use client";

import { useState, useEffect } from "react";
import { Sparkle } from "@phosphor-icons/react";
import { useI18n } from "@/i18n/I18nProvider";
import DurationSlider from "./DurationSlider";
import { startS1StepByStep, runS1Step, isDemoMode } from "./api";



import { errorMessage } from "@/lib/errors";
interface Props {
  config: any;  // The config from SceneForm
  onBack: () => void;
  onStart: (finalConfig: any) => void;
}

export default function RecommendPanel({ config, onBack, onStart }: Props) {
  const { t } = useI18n();
  const [loading, setLoading] = useState(true);
  const [duration, setDuration] = useState(30);
  const [platforms, setPlatforms] = useState<string[]>(config.target_platforms || []);
  const [summary, setSummary] = useState("");
  const [tone, setTone] = useState("");
  const [mode, setMode] = useState<"expert" | "smart">("expert");
  const [error, setError] = useState("");

  const [starting, setStarting] = useState(false);
  useEffect(() => {
    fetchRecommendation();
  }, []);

  async function fetchRecommendation() {
    // Demo mode: use mock data, skip all API calls
    if (isDemoMode()) {
      try {
        const { DEMO_RESULT_1, DEMO_RESULT_2 } = await import("@/demo-data");
        const isBrand = config.content_scenario === "brand_campaign";
        const demoResult = isBrand ? DEMO_RESULT_2 : DEMO_RESULT_1;
        const firstBrief = demoResult.briefs?.[0];

        if (firstBrief) {
          setSummary(firstBrief.key_message || firstBrief.topic || "");
          setTone(firstBrief.hook_type || "");
        }
        setPlatforms(config.target_platforms || ["tiktok", "shopify"]);
        setDuration(config.video_duration || 30);
        setLoading(false);
      } catch (e: unknown) {
        setError(errorMessage(e, "Failed to load demo recommendation"));
        setLoading(false);
      }
      return;
    }

    try {
      // Initialize pipeline and run strategy step
      const initResult = await startS1StepByStep({ ...config, mode: "step_by_step" });
      const label = initResult.label;
      const strategyResult = await runS1Step(label, "strategy");

      // Extract recommendation from strategy output
      const briefs = strategyResult?.data || strategyResult?.steps?.strategy?.output || [];
      const firstBrief = Array.isArray(briefs) ? briefs[0] : briefs;

      if (firstBrief) {
        setSummary(firstBrief.key_message || firstBrief.topic || "");
        setTone(firstBrief.tone || "");
      }

      // Platforms from config
      setPlatforms(config.target_platforms || ["tiktok", "shopify"]);

      // AI-recommended duration — infer from strategy or default to 30
      setDuration(config.video_duration || 30);

      setLoading(false);
    } catch (e: unknown) {
      setError(errorMessage(e, "Failed to get recommendation"));
      setLoading(false);
    }
  }

  function handleStart() {
    if (starting) return;
    setStarting(true);
    onStart({
      ...config,
      video_duration: duration,
      target_platforms: platforms,
      mode: mode === "smart" ? "auto" : "step_by_step",
    });
  }

  if (loading) {
    return (
      <div className="apple-card p-6 text-center">
        <div className="animate-spin w-8 h-8 border-2 border-[var(--fortune-red)] border-t-transparent rounded-full mx-auto mb-3" />
        <p className="text-sm text-[var(--text-body)]">{t("recommend.analyzing")}</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="apple-card p-6 text-center">
        <p className="text-sm text-[var(--crimson-mist)] mb-3">{error}</p>
        <button onClick={onBack} className="apple-btn text-xs">{t("common.back")}</button>
      </div>
    );
  }

  return (
    <div className="space-y-3 animate-slide-up">
      <div className="apple-card p-4">
        <div className="flex items-center gap-2 mb-4">
          <Sparkle size={20} weight="fill" className="text-[var(--fortune-red)]" />
          <h2 className="text-base font-semibold text-[var(--text-h1)]">{t("recommend.title")}</h2>
        </div>
        <p className="text-xs text-[var(--text-body)] mb-4">{t("recommend.subtitle")}</p>

        {/* Duration Recommendation */}
        <div className="mb-4">
          <DurationSlider value={duration} onChange={setDuration} />
        </div>

        {/* Platform Recommendation */}
        <div className="apple-card p-3 mb-4 bg-[var(--bg-panel)]">
          <h4 className="text-[12px] font-semibold text-[var(--text-body)] uppercase tracking-wider mb-2">
            {t("recommend.platforms")}
          </h4>
          <div className="flex flex-wrap gap-2">
            {["tiktok", "shopify", "instagram", "youtube_shorts"].map(p => {
              const active = platforms.includes(p);
              return (
                <button
                  key={p}
                  onClick={() => setPlatforms(prev =>
                    prev.includes(p) ? prev.filter(x => x !== p) : [...prev, p]
                  )}
                  className={`text-xs px-3 py-1 rounded-full transition-all ${
                    active
                      ? "bg-[var(--fortune-red)] text-white"
                      : "bg-[var(--bg-card)] text-[var(--text-body)] border border-[var(--border-default)] hover:border-[var(--fortune-red)]"
                  }`}
                >
                  {t(`platform.${p}`)}
                </button>
              );
            })}
          </div>
        </div>

        {/* Strategy Summary */}
        {summary && (
          <div className="apple-card p-3 mb-4 bg-[var(--bg-panel)]">
            <h4 className="text-[12px] font-semibold text-[var(--text-body)] uppercase tracking-wider mb-1">
              {t("recommend.strategy")}
            </h4>
            <p className="text-xs text-[var(--text-h1)] leading-relaxed">{summary}</p>
            {tone && <p className="text-[12px] text-[var(--text-muted)] mt-1">{t("recommend.tone")}: {tone}</p>}
          </div>
        )}

        {/* Mode Selector */}
        <div className="flex items-center gap-4 mb-4">
          <span className="text-[12px] font-semibold text-[var(--text-body)]">{t("recommend.mode")}:</span>
          <button
            onClick={() => setMode("smart")}
            className={`text-xs px-3 py-1.5 rounded-full transition-all ${
              mode === "smart" ? "bg-[var(--cinema-azure)] text-white" : "bg-[var(--bg-panel)] text-[var(--text-body)] hover:bg-[var(--border-default)]"
            }`}
          >
            {t("mode.smartCreate")}
          </button>
          <button
            onClick={() => setMode("expert")}
            className={`text-xs px-3 py-1.5 rounded-full transition-all ${
              mode === "expert" ? "bg-[var(--fortune-red)] text-white" : "bg-[var(--bg-panel)] text-[var(--text-body)] hover:bg-[var(--border-default)]"
            }`}
          >
            {t("mode.expertStudio")}
          </button>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="flex justify-between">
        <button onClick={onBack} className="apple-btn text-xs px-4 py-2">
          {"←"} {t("recommend.backToEdit")}
        </button>
        <button onClick={handleStart} disabled={starting} className="apple-btn apple-btn-primary text-xs px-6 py-2">
          {starting ? t("common.loading") : t("recommend.startGenerating")} {starting ? "" : "→"}
        </button>
      </div>
    </div>
  );
}
