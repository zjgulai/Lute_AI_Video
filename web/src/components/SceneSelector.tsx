"use client";

import React, { useState, useEffect } from "react";
import {
  CONTENT_SCENARIOS,
  PLATFORM_LABELS,
} from "./types";
import {
  Users, Megaphone, Package,
  ShoppingBag, Music, MessageCircle, Video, ShoppingCart, ExternalLink,
  Clock, FileText, CheckCircle, Image, Search, PenSquare, Headphones, Type, BarChart3, Repeat,
} from "lucide-react";
import AssetUploader from "./AssetUploader";
import PortfolioGallery from "./PortfolioGallery";
import { setApiKey } from "./api";
import { useI18n } from "@/i18n/I18nProvider";

const SCENE_ICON_MAP: Record<string, React.ComponentType<{ size?: number; strokeWidth?: number; className?: string }>> = {
  product_direct: Package,
  brand_campaign: Megaphone,
  influencer_remix: Users,
};

const PLATFORM_ICON_MAP: Record<string, React.ComponentType<{ size?: number; strokeWidth?: number; className?: string }>> = {
  shopify: ShoppingBag,
  amazon: ShoppingCart,
  tiktok: Music,
  reddit: MessageCircle,
  facebook: ExternalLink,
  youtube_shorts: Video,
};

const STAGE_ICON_MAP: Record<string, React.ComponentType<{ size?: number; strokeWidth?: number; className?: string }>> = {
  strategy: Clock,
  script: FileText,
  compliance: CheckCircle,
  storyboard: Image,
  asset_sourcing: Search,
  media_gen: Video,
  editing: PenSquare,
  audio: Headphones,
  caption: Type,
  thumbnail: Image,
  analytics: BarChart3,
  distribution: Repeat,
};

interface Props {
  onStart: (config: any) => void;
  loading: boolean;
  pipelineMode?: "auto" | "step_by_step";
  onModeChange?: (mode: "auto" | "step_by_step") => void;
}

const SCENARIO_DETAILS: Record<string, { descKey: string; platformsKey: string; exampleKey: string }> = {
  influencer_remix: {
    descKey: "scene.desc.influencer_remix",
    platformsKey: "scene.platforms.influencer_remix",
    exampleKey: "scene.example.influencer_remix",
  },
  brand_campaign: {
    descKey: "scene.desc.brand_campaign",
    platformsKey: "scene.platforms.brand_campaign",
    exampleKey: "scene.example.brand_campaign",
  },
  product_direct: {
    descKey: "scene.desc.product_direct",
    platformsKey: "scene.platforms.product_direct",
    exampleKey: "scene.example.product_direct",
  },
};

export default function SceneSelector({ onStart, loading, pipelineMode = "step_by_step", onModeChange }: Props) {
  const { t } = useI18n();
  const [productName, setProductName] = useState("孕妇枕");
  const [brandName, setBrandName] = useState("Momcozy");
  const [uspsStr, setUspsStr] = useState("");
  const [selectedScenario, setSelectedScenario] = useState<string>(
    CONTENT_SCENARIOS[0].id
  );
  const [selectedPlatforms, setSelectedPlatforms] = useState<string[]>([
    ...CONTENT_SCENARIOS[0].platforms,
  ]);
  const [showApiKeys, setShowApiKeys] = useState(false);
  const [uploadedAssets, setUploadedAssets] = useState<any[]>([]);
  const [videoDuration, setVideoDuration] = useState(10);
  const [apiKeys, setApiKeys] = useState<Record<string, string>>({});
  const [backendApiKey, setBackendApiKey] = useState("");

  const scenario = CONTENT_SCENARIOS.find((s) => s.id === selectedScenario);
  useEffect(() => {
    if (scenario) {
      setSelectedPlatforms([...scenario.platforms]);
    }
  }, [selectedScenario]);

  const apiFields = [
    { key: "POYO_API_KEY", labelKey: "apikey.poyo", noteKey: "apikey.poyoNote", url: "https://poyo.ai" },
    { key: "OPENAI_API_KEY", labelKey: "apikey.openai", noteKey: "apikey.openaiNote", url: "https://platform.openai.com/api-keys" },
    { key: "ANTHROPIC_API_KEY", labelKey: "apikey.claude", noteKey: "apikey.claudeNote", url: "https://console.anthropic.com/settings/keys" },
    { key: "ELEVENLABS_API_KEY", labelKey: "apikey.elevenlabs", noteKey: "apikey.elevenlabsNote", url: "https://elevenlabs.io/speech-synthesis" },
  ];

  const handleStart = () => {
    if (!productName) return;
    if (backendApiKey.trim()) {
      setApiKey(backendApiKey.trim());
    }
    const usps = uspsStr
      .split("\n")
      .filter(Boolean)
      .map((t, i) => ({ priority: i === 0 ? "P0" : i === 1 ? "P1" : "P2", text: t.trim() }));
    const filledKeys = Object.fromEntries(Object.entries(apiKeys).filter(([, v]) => v.trim() !== ""));
    onStart({
      product_catalog: { products: [{ name: productName, usps, specs: { weight: "220g", battery_life: "2.5h" }, certifications: ["FDA", "CE"] }] },
      brand_guidelines: { brand_name: brandName, tone_of_voice: { archetype: "Caregiver", keywords: ["warm", "empowering"] } },
      target_platforms: selectedPlatforms,
      target_languages: ["en"],
      content_calendar_week: getCurrentWeek(),
      content_scenario: selectedScenario,
      uploaded_assets: uploadedAssets.map(a => a.path),
      ...(Object.keys(filledKeys).length > 0 ? { api_keys: filledKeys } : {}),
    });
  };

  const detail = SCENARIO_DETAILS[selectedScenario] || SCENARIO_DETAILS.product_direct;
  // Resolve translated scene details
  const detailDesc = t(detail.descKey);
  const detailPlatforms = t(detail.platformsKey);
  const detailExample = t(detail.exampleKey);

  return (
    <div className="grid grid-cols-[1fr_1fr] gap-4 min-h-full">
      {/* ── Left column: form ── */}
      <div className="space-y-3">
        {/* Scenario Picker */}
        <div className="apple-card p-3 space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="text-[11px] font-semibold text-[#59585E] uppercase tracking-wider">{t("scene.contentScenario")}</h3>
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => onModeChange?.("step_by_step")}
                className={`text-[11px] px-2 py-0.5 rounded-full font-medium transition-all cursor-pointer ${
                  pipelineMode === "step_by_step"
                    ? "bg-[#6A2B3A] text-white"
                    : "bg-[#FCE4E2] text-[#59585E] hover:bg-[#EDD3D1]"
                }`}
              >
                {t("pipeline.stepByStep")}
              </button>
              <button
                onClick={() => onModeChange?.("auto")}
                className={`text-[11px] px-2 py-0.5 rounded-full font-medium transition-all cursor-pointer ${
                  pipelineMode === "auto"
                    ? "bg-[#6A2B3A] text-white"
                    : "bg-[#FCE4E2] text-[#59585E] hover:bg-[#EDD3D1]"
                }`}
              >
                {t("pipeline.auto")}
              </button>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-1.5">
            {CONTENT_SCENARIOS.map((s) => {
              const active = selectedScenario === s.id;
              return (
                <button
                  key={s.id}
                  onClick={() => setSelectedScenario(s.id)}
                  className={`text-left p-2 rounded-lg border transition-all cursor-pointer ${
                    active
                      ? "border-[#6A2B3A] bg-[#6A2B3A]/5 ring-1 ring-[#6A2B3A]/20"
                      : "border-[#EDD3D1] bg-white hover:border-[#D9A8A3]"
                  }`}
                >
                  {React.createElement(SCENE_ICON_MAP[s.id] || Package, { size: 24, strokeWidth: 1.5, className: "block mb-0.5 text-[#6A2B3A]" })}
                  <span className={`text-[11px] font-semibold block ${active ? "text-[#6A2B3A]" : "text-[#35353B]"}`}>
                    {t(`scene.${s.id}.title`)}
                  </span>
                  <span className="text-[11px] text-[#9FA0A0] mt-0.5 block leading-tight line-clamp-2">
                    {t(`scene.${s.id}.desc`)}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Product Config */}
        <div className="apple-card p-3 space-y-2">
          <h3 className="text-[11px] font-semibold text-[#59585E] uppercase tracking-wider">{t("product.title")}</h3>
          <div>
            <label className="block text-[11px] font-medium text-[#59585E] mb-1">
              {t("product.nameRequired")}
            </label>
            <input
              type="text"
              value={productName}
              onChange={(e) => setProductName(e.target.value)}
              placeholder={t("product.namePlaceholder")}
              className="apple-input text-sm"
            />
          </div>
          <div>
            <label className="block text-[11px] font-medium text-[#59585E] mb-1">{t("product.usps")}</label>
            <textarea
              value={uspsStr}
              onChange={(e) => setUspsStr(e.target.value)}
              placeholder={t("product.uspsPlaceholder")}
              className="apple-input resize-none text-sm"
              rows={2}
            />
            <p className="text-[11px] text-[#9FA0A0] mt-0.5">{t("product.uspHint")}</p>
          </div>
          <div>
            <label className="block text-[11px] font-medium text-[#59585E] mb-1">{t("product.brandName")}</label>
            <input
              type="text" value={brandName}
              onChange={(e) => setBrandName(e.target.value)}
              placeholder={t("product.brandPlaceholder")} className="apple-input text-sm"
            />
          </div>
          {(selectedScenario === "product_direct" || selectedScenario === "live_shoot_to_video") && (
            <div>
              <label className="block text-[11px] font-medium text-[#59585E] mb-1">{t("workflow.duration")}</label>
              <div className="flex gap-1.5">
                {[5, 7, 10].map((duration) => (
                  <button
                    key={duration}
                    onClick={() => setVideoDuration(duration)}
                    className={`apple-pill text-xs py-1 px-2.5 ${videoDuration === duration ? "active" : ""}`}
                  >
                    {duration}s
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Asset Upload */}
        <div className="apple-card p-3 space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="text-[11px] font-semibold text-[#59585E] uppercase tracking-wider">{t("upload.title")}</h3>
            {uploadedAssets.length > 0 && (
              <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-[#6A2B3A]/10 text-[#6A2B3A]">
                {uploadedAssets.length}{t("upload.count")}
              </span>
            )}
          </div>
          <AssetUploader onUpload={(results) => setUploadedAssets(prev => [...prev, ...results])} />
        </div>

        {/* Platform Chips */}
        <div className="apple-card p-3 space-y-2">
          <h3 className="text-[11px] font-semibold text-[#59585E] uppercase tracking-wider">{t("distPlatform")}</h3>
          <div className="flex flex-wrap gap-1.5">
            {Object.keys(PLATFORM_LABELS).map((id) => {
              const active = selectedPlatforms.includes(id);
              return (
                <button
                  key={id}
                  onClick={() =>
                    setSelectedPlatforms((prev) =>
                      prev.includes(id) ? prev.filter((p) => p !== id) : [...prev, id]
                    )
                  }
                  className={`apple-pill text-xs py-1 px-2.5 ${active ? "active" : ""}`}
                >
                  {React.createElement(PLATFORM_ICON_MAP[id] || ShoppingBag, { size: 12, strokeWidth: 1.5 })}
                  {t("platform." + id)}
                </button>
              );
            })}
          </div>
        </div>

        {/* Start + footer */}
        <button
          onClick={handleStart}
          disabled={loading || !productName}
          className="apple-btn apple-btn-primary w-full py-2.5 text-sm"
        >
          {loading ? (
            <span className="flex items-center gap-2">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" className="animate-spin">
                <circle cx="12" cy="12" r="10" stroke="rgba(255,255,255,0.3)" strokeWidth="3" />
                <path d="M12 2a10 10 0 0 1 10 10" stroke="white" strokeWidth="3" strokeLinecap="round" />
              </svg>
              {t("common.redirecting")}
            </span>
          ) : (
            <>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                <polygon points="7,5 19,12 7,19" fill="white" />
              </svg>
              {t("product.configured")}
            </>
          )}
        </button>
        <p className="text-[11px] text-[#9FA0A0]">
          {pipelineMode === "step_by_step"
            ? t("pipeline.stepByStepHint")
            : t("pipeline.autoHint")}
        </p>
      </div>

      {/* ── Right column: scenario preview ── */}
      <div className="apple-card p-4 space-y-3">
        {/* Active scenario highlight */}
        {scenario && (
          <>
            <div className="flex items-center gap-3 pb-3 border-b border-[#EDD3D1]">
              <span className="w-9 h-9 rounded-xl bg-[#6A2B3A]/5 text-[#6A2B3A] flex items-center justify-center shrink-0">
                {React.createElement(SCENE_ICON_MAP[scenario.id] || Package, { size: 20, strokeWidth: 1.5 })}
              </span>
              <div>
                <h2 className="text-base font-semibold text-[#35353B]">{t(`scene.${scenario.id}.title`)}</h2>
                <p className="text-xs text-[#6A2B3A] font-medium">{scenario.id === "influencer_remix" ? t("scene.defaultScenario") : t("scene.manualSelect")}</p>
              </div>
            </div>

            <div className="space-y-3">
              <div>
                <h4 className="text-[11px] font-semibold text-[#59585E] uppercase tracking-wider mb-1">{t("scene.description")}</h4>
                <p className="text-xs text-[#35353B] leading-relaxed">{detailDesc}</p>
              </div>

              <div>
                <h4 className="text-[11px] font-semibold text-[#59585E] uppercase tracking-wider mb-1">{t("scene.recommendedPlatforms")}</h4>
                <div className="flex flex-wrap gap-1.5">
                  {scenario.platforms.map((p: string) => (
                    <span key={p} className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full bg-[#6A2B3A]/5 text-[#6A2B3A] border border-[#6A2B3A]/15">
                      {React.createElement(PLATFORM_ICON_MAP[p] || ShoppingBag, { size: 12, strokeWidth: 1.5 })}
                      {t("platform." + p)}
                    </span>
                  ))}
                </div>
              </div>

              <div>
                <h4 className="text-[11px] font-semibold text-[#59585E] uppercase tracking-wider mb-1">{t("scene.typicalFlow")}</h4>
                <div className="flex items-center gap-1.5 text-[11px] text-[#59585E]">
                  {detailExample.split("→").map((step, i) => (
                    <span key={i} className="flex items-center gap-1">
                      <span className="w-4 h-4 rounded-full bg-[#FCE4E2] flex items-center justify-center text-[11px] font-semibold text-[#9FA0A0]">{i + 1}</span>
                      <span>{step.trim()}</span>
                      {i < detailExample.split("→").length - 1 && <span className="text-[#9FA0A0]">→</span>}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            {/* Pipeline steps preview */}
            <div className="pt-3 border-t border-[#EDD3D1]">
              <h4 className="text-[11px] font-semibold text-[#59585E] uppercase tracking-wider mb-2">{t("pipeline.progress")} (16)</h4>
              <div className="grid grid-cols-4 gap-1">
                {[
                  { labelKey: "pstage.strategy", key: "strategy", done: true },
                  { labelKey: "pstage.script", key: "script", done: true },
                  { labelKey: "pipeline.selfAudited", key: "compliance", done: true },
                  { labelKey: "pstage.compliance", key: "compliance", done: true },
                  { labelKey: "pstage.storyboard", key: "storyboard", done: true },
                  { labelKey: "pstage.asset_sourcing", key: "asset_sourcing", done: true },
                  { labelKey: "pstage.media_gen", key: "media_gen", done: false },
                  { labelKey: "pstage.editing", key: "editing", done: true },
                  { labelKey: "pstage.audio", key: "audio", done: true },
                  { labelKey: "pstage.caption", key: "caption", done: true },
                  { labelKey: "pstage.thumbnail", key: "thumbnail", done: true },
                  { labelKey: "pipeline.selfAudited", key: "compliance", done: true },
                  { labelKey: "step.audit", key: "analytics", done: true },
                  { labelKey: "pstage.distribution", key: "distribution", done: true },
                  { labelKey: "pstage.analytics", key: "analytics", done: false },
                  { labelKey: "step.allDone", key: "thumbnail", done: true },
                ].map((step, i) => (
                  <div key={i}
                    className={`text-center p-1 rounded-md ${step.done ? "bg-[#FCE4E2]" : "bg-[#FCE4E2]/50"}`}
                  >
                    {React.createElement(STAGE_ICON_MAP[step.key] || Clock, { size: 16, strokeWidth: 1.5, className: "w-4 h-4 mx-auto text-[#59585E]" })}
                    <span className={`text-[8px] font-medium ${step.done ? "text-[#59585E]" : "text-[#9FA0A0]"}`}>
                      {t(step.labelKey)}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Portfolio Gallery */}
            <PortfolioGallery />
          </>
        )}
      </div>

      {/* ── Floating API Key button (bottom-right corner) ── */}
      <div className="fixed bottom-5 right-5 z-50 flex flex-col items-end gap-2">
        {showApiKeys && (
          <div className="apple-card p-3 w-72 animate-scale-in shadow-xl bg-white/95 backdrop-blur-sm border border-[#EDD3D1] rounded-xl">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[11px] font-semibold text-[#59585E] uppercase tracking-wider">{t("apikey.title")}</span>
              <button onClick={() => setShowApiKeys(false)}
                className="text-[#9FA0A0] hover:text-[#35353B] transition-colors cursor-pointer p-0.5">
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                  <path d="M2.5 2.5L9.5 9.5M9.5 2.5L2.5 9.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
              </button>
            </div>
            <p className="text-[11px] text-[#9FA0A0] mb-2">{t("apikey.hint")}</p>
            <div className="space-y-1.5">
              <div>
                <label className="block text-[11px] font-medium text-[#ff9500] mb-0.5">{t("apikey.backend")}</label>
                <input
                  type="password"
                  value={backendApiKey}
                  onChange={(e) => setBackendApiKey(e.target.value)}
                  placeholder={t("apikey.backendPlaceholder")}
                  className="apple-input text-xs w-full"
                />
                <p className="text-[11px] text-[#9FA0A0] mt-0.5">{t("apikey.backendHint")}</p>
              </div>
              <div className="border-t border-[#EDD3D1] pt-1.5" />
              {apiFields.map((f) => (
                <div key={f.key}>
                  <label className="block text-[11px] font-medium text-[#59585E] mb-0.5">{t(f.labelKey)}</label>
                  <div className="flex gap-1">
                    <input type="password" value={apiKeys[f.key] || ""}
                      onChange={(e) => setApiKeys({ ...apiKeys, [f.key]: e.target.value })}
                      placeholder={t("apikey.inputPlaceholder")} className="apple-input text-xs flex-1" />
                    {f.url && (
                      <a href={f.url} target="_blank"
                        className="shrink-0 flex items-center px-2 text-[11px] text-[#6A2B3A] bg-[#6A2B3A]/5 rounded-lg hover:bg-[#6A2B3A]/10 border border-[#6A2B3A]/20 transition-colors no-underline whitespace-nowrap">
                        {t("apikey.apply")}
                      </a>
                    )}
                  </div>
                  {f.noteKey && <p className="text-[11px] text-[#9FA0A0] mt-0.5">{t(f.noteKey)}</p>}
                </div>
              ))}
            </div>
          </div>
        )}
        <button onClick={() => setShowApiKeys(!showApiKeys)}
          className="w-9 h-9 rounded-full bg-[#6A2B3A] text-white shadow-lg hover:bg-[#4E1F2A] hover:shadow-xl active:scale-95 transition-all cursor-pointer flex items-center justify-center"
          title={t("apikey.title")}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="11" width="18" height="11" rx="2" />
            <path d="M7 11V7a5 5 0 0 1 10 0v4" />
          </svg>
        </button>
      </div>
    </div>
  );
}

function getCurrentWeek(): string {
  const now = new Date();
  const start = new Date(now.getFullYear(), 0, 1);
  const diff = (now.getTime() - start.getTime() + 86400000) / 86400000;
  const week = Math.ceil(diff / 7);
  return `${now.getFullYear()}-W${String(week).padStart(2, "0")}`;
}
