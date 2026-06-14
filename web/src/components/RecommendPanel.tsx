"use client";

import { useState, useEffect, useCallback } from "react";
import { Sparkle } from "@phosphor-icons/react";
import { useI18n } from "@/i18n/I18nProvider";
import DurationSlider from "./DurationSlider";
import { startS1StepByStep, runS1Step, isDemoMode } from "./api";
import { errorMessage } from "@/lib/errors";

interface Props {
  config: Record<string, unknown>;  // The config from SceneForm
  onBack: () => void;
  onStart: (finalConfig: Record<string, unknown>) => void;
}

type LocalRecommendation = {
  summary: string;
  tone: string;
  platforms: string[];
  duration: number;
};

function textValue(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function firstProductName(productCatalog: unknown): string {
  if (!productCatalog || typeof productCatalog !== "object") return "";
  const catalog = productCatalog as Record<string, unknown>;
  const products = catalog.products;
  if (!Array.isArray(products) || products.length === 0) return "";
  const first = products[0];
  if (!first || typeof first !== "object") return "";
  const product = first as Record<string, unknown>;
  return textValue(product.name) || textValue(product.product_name);
}

function toneFromGuidelines(brandGuidelines: unknown): string {
  if (!brandGuidelines || typeof brandGuidelines !== "object") return "";
  const guidelines = brandGuidelines as Record<string, unknown>;
  const tone = guidelines.tone_of_voice;
  if (typeof tone === "string") return tone.trim();
  if (!tone || typeof tone !== "object") return "";
  const toneObject = tone as Record<string, unknown>;
  const keywords = toneObject.keywords;
  if (Array.isArray(keywords)) {
    return keywords.map((item) => textValue(item)).filter(Boolean).join(", ");
  }
  return textValue(toneObject.archetype);
}

export function buildLocalRecommendation(config: Record<string, unknown>): LocalRecommendation {
  const scenario = textValue(config.content_scenario);
  const productName = firstProductName(config.product_catalog);
  const platforms = Array.isArray(config.target_platforms)
    ? config.target_platforms.map((item) => textValue(item)).filter(Boolean)
    : ["tiktok", "shopify"];
  const duration = typeof config.video_duration === "number" ? config.video_duration : 30;

  if (scenario === "brand_campaign") {
    return {
      summary: textValue(config.key_message) || textValue(config.campaign_theme) || "Brand campaign auto execution",
      tone: toneFromGuidelines(config.brand_guidelines),
      platforms,
      duration,
    };
  }
  if (scenario === "influencer_remix") {
    return {
      summary: productName
        ? `Remix creator content around ${productName}`
        : "Influencer remix auto execution",
      tone: textValue(config.influencer_name),
      platforms,
      duration,
    };
  }
  if (scenario === "brand_vlog") {
    return {
      summary: textValue(config.story_description) || "Brand VLOG auto execution",
      tone: textValue(config.scene_id),
      platforms,
      duration,
    };
  }
  return {
    summary: productName ? `Product direct story for ${productName}` : "Product direct workflow",
    tone: toneFromGuidelines(config.brand_guidelines),
    platforms,
    duration,
  };
}

export default function RecommendPanel({ config, onBack, onStart }: Props) {
  const { t } = useI18n();
  const stepByStepSupported = config.content_scenario === "product_direct";
  const [loading, setLoading] = useState(true);
  const [duration, setDuration] = useState(30);
  const [platforms, setPlatforms] = useState<string[]>((config.target_platforms as string[]) || []);
  const [summary, setSummary] = useState("");
  const [tone, setTone] = useState("");
  const [mode, setMode] = useState<"expert" | "smart">(stepByStepSupported ? "expert" : "smart");
  const [error, setError] = useState("");

  const [starting, setStarting] = useState(false);

  const fetchRecommendation = useCallback(async () => {
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
        setPlatforms((config.target_platforms as string[]) || ["tiktok", "shopify"]);
        setDuration((config.video_duration as number) || 30);
        setLoading(false);
      } catch (e: unknown) {
        setError(errorMessage(e, "Failed to load demo recommendation"));
        setLoading(false);
      }
      return;
    }

    if (!stepByStepSupported) {
      const localRecommendation = buildLocalRecommendation(config);
      setSummary(localRecommendation.summary);
      setTone(localRecommendation.tone);
      setPlatforms(localRecommendation.platforms);
      setDuration(localRecommendation.duration);
      setLoading(false);
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
      setPlatforms((config.target_platforms as string[]) || ["tiktok", "shopify"]);

      // AI-recommended duration — infer from strategy or default to 30
      setDuration((config.video_duration as number) || 30);

      setLoading(false);
    } catch (e: unknown) {
      setError(errorMessage(e, "Failed to get recommendation"));
      setLoading(false);
    }
  }, [config, stepByStepSupported]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchRecommendation();
  }, [fetchRecommendation]);

  function handleStart() {
    if (starting) return;
    setStarting(true);
    const selectedMode = stepByStepSupported ? mode : "smart";
    onStart({
      ...config,
      video_duration: duration,
      target_platforms: platforms,
      mode: selectedMode === "smart" ? "auto" : "step_by_step",
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
            onClick={() => stepByStepSupported && setMode("expert")}
            disabled={!stepByStepSupported}
            className={`text-xs px-3 py-1.5 rounded-full transition-all ${
              !stepByStepSupported ? "opacity-50 cursor-not-allowed" : ""
            } ${
              mode === "expert" ? "bg-[var(--fortune-red)] text-white" : "bg-[var(--bg-panel)] text-[var(--text-body)] hover:bg-[var(--border-default)]"
            }`}
          >
            {t("mode.expertStudio")}
          </button>
        </div>
        {!stepByStepSupported && (
          <p className="text-[11px] text-[var(--text-muted)] mb-4">{t("pipeline.stepByStepS1Only")}</p>
        )}
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
