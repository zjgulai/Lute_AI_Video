"use client";

import React, { useState } from "react";
import { Users, Megaphone, Package, ShoppingBag, MusicNotes, ChatCircle, VideoCamera, ShoppingCart, ArrowSquareOut, Camera } from "@phosphor-icons/react";
import type { IconProps } from "@phosphor-icons/react";
import { PLATFORM_LABELS, CONTENT_SCENARIOS } from "./types";
import { useI18n } from "@/i18n/I18nProvider";
import VlogSixView from "./VlogSixView";
import VlogModelSelector from "./VlogModelSelector";
import { VLOG_BRANDS, VLOG_MODELS, VLOG_SCENES, VLOG_DURATION_OPTIONS } from "@/demo-data";
import GuidedForm from "./GuidedForm";

const USE_GUIDED_FORM = process.env.NEXT_PUBLIC_USE_GUIDED_FORM !== "false";

interface Props {
  scene: string;
  onSubmit: (config: Record<string, unknown>) => void;
  loading: boolean;
  fieldErrors?: Record<string, string>;
}

const CATEGORIES = ["Home", "Baby", "Electronics", "Health", "Fashion", "Other"];

const BRAND_PACKAGES = [
  { id: "bp_default", nameKey: "brand.packageName" },
];

const PLATFORM_ICON_MAP: Record<string, React.ComponentType<IconProps>> = {
  shopify: ShoppingBag,
  amazon: ShoppingCart,
  tiktok: MusicNotes,
  reddit: ChatCircle,
  facebook: ArrowSquareOut,
  youtube_shorts: VideoCamera,
};

export default function SceneForm({ scene, onSubmit, loading, fieldErrors }: Props) {
  const { t } = useI18n();
  const [mode, setMode] = useState<"expert" | "smart">("expert");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [showProductDetails, setShowProductDetails] = useState(false);

  // S1 fields
  const [productName, setProductName] = useState("Trunk Baby Organizer");
  const [brandName, setBrandName] = useState("Momcozy");
  const [keyFeatures, setKeyFeatures] = useState("Quick-grab access, no digging through trunk\n5 clear compartments for diapers, wipes, snacks, clothes, toys\nStays stable in car, no rolling or tipping\nCollapsible when not in use\nBoth parents can find everything instantly");
  const [category, setCategory] = useState("Baby");
  const [continuityMode, setContinuityMode] = useState("standard");

  // S1 Product Details (expandable)
  const [usageScenario, setUsageScenario] = useState("Car trunk, family outings — daycare drop-offs, park trips, grocery runs, weekend road trips. Keeps baby essentials permanently organized so you never repack.");
  const [painPoints, setPainPoints] = useState("Trunk becomes chaos after one short trip with baby\nWipes, snacks, diapers scattered across different bags\nCan't find backup clothes when you actually need them\nItems roll around and get lost under seats\nPartner or grandparents don't know where anything is");
  const [productTargetAudience, setProductTargetAudience] = useState("New parents 25-35, dual-income families who drive daily, weekend trip families, small-car urban families");
  const [competitorContext, setCompetitorContext] = useState("Generic plastic bins — no baby-specific compartments\nSoft-sided organizers — collapse under weight, hard to clean\nMost solutions — no labels, everyone just throws things in");

  // S1 Brand Voice (expandable)
  const [showBrandVoice, setShowBrandVoice] = useState(false);
  const [brandVoiceDo, setBrandVoiceDo] = useState("Family outings should feel easier, not like a packing mission\nOne less thing to think about before you leave\nDesigned for real parenting days");
  const [brandVoiceDont, setBrandVoiceDont] = useState("Revolutionary organizing technology\nBUY NOW limited stock\nDoctors recommend this one weird trunk hack");

  // S2 fields
  const [brandPackage, setBrandPackage] = useState("");
  const [campaignTheme, setCampaignTheme] = useState("");
  const [keyMessage, setKeyMessage] = useState("");
  const [brandTargetAudience, setBrandTargetAudience] = useState("");

  // S2 Campaign Details (expandable)
  const [showCampaignDetails, setShowCampaignDetails] = useState(false);
  const [campaignGoal, setCampaignGoal] = useState("");
  const [brandValues, setBrandValues] = useState("");
  const [visualIdentity, setVisualIdentity] = useState("");
  const [competitorCampaigns, setCompetitorCampaigns] = useState("");

  // S3 fields
  const [videoUrl, setVideoUrl] = useState("");
  const [productToFeature, setProductToFeature] = useState("");
  const [influencerName, setInfluencerName] = useState("");
  const [keepOriginalAudio, setKeepOriginalAudio] = useState(true);

  // Brand VLOG state
  const [vlogBrandId, setVlogBrandId] = useState("momcozy");
  const [vlogProductId, setVlogProductId] = useState("m5");
  const [vlogSceneId, setVlogSceneId] = useState("living-room");
  const [vlogModelIds, setVlogModelIds] = useState<string[]>([]);
  const [vlogStory, setVlogStory] = useState("");
  const [vlogDurationId, setVlogDurationId] = useState("15-30");

  // Shared advanced fields
  const [selectedPlatforms, setSelectedPlatforms] = useState<string[]>(() => {
    const scenario = CONTENT_SCENARIOS.find((s) => s.id === scene);
    return scenario ? [...scenario.platforms] : [];
  });

  const handleSubmit = () => {
    const usps = keyFeatures
      .split("\n")
      .filter(Boolean)
      .map((text, i) => ({
        priority: i === 0 ? "P0" : i === 1 ? "P1" : "P2",
        text: text.trim(),
      }));

    const config: Record<string, unknown> = {
      content_scenario: scene,
      target_platforms: selectedPlatforms,
      target_languages: ["en"],
      content_calendar_week: getCurrentWeek(),
      mode,
    };

    if (scene === "brand_vlog") {
      config.mode = "auto";
    }

    if (scene === "product_direct") {
      if (!productName) return;
      config.storyboard_grid = "12";
      config.transition_style = "match_cut";
      config.continuity_mode = continuityMode === "high_quality" ? "high_quality" : "standard";
      config.product_catalog = {
        products: [{
          name: productName,
          usps,
          category: category || "Other",
          usage_scenario: usageScenario,
          pain_points: painPoints.split("\n").filter(Boolean),
          target_audience: productTargetAudience,
          competitor_context: competitorContext.split("\n").filter(Boolean),
        }],
      };
      config.brand_guidelines = {
        brand_name: brandName || "",
        tone_of_voice: {
          archetype: "Caregiver",
          keywords: ["warm", "empowering"],
          do_examples: brandVoiceDo.split("\n").filter(Boolean),
          dont_examples: brandVoiceDont.split("\n").filter(Boolean),
        },
      };
    } else if (scene === "brand_campaign") {
      if (!brandPackage) return;
      config.brand_package = brandPackage;
      config.campaign_theme = campaignTheme || "";
      config.key_message = keyMessage || "";
      config.target_audience = brandTargetAudience || "";
      config.brand_guidelines = {
        brand_name: "",
        tone_of_voice: {},
        campaign_goal: campaignGoal,
        brand_values: brandValues.split("\n").filter(Boolean),
        visual_identity: visualIdentity,
        competitor_campaigns: competitorCampaigns.split("\n").filter(Boolean),
      };
      config.product_catalog = { products: [] };
      config.storyboard_grid = "12";
      config.transition_style = "match_cut";
      config.continuity_mode = continuityMode === "high_quality" ? "high_quality" : "standard";
    } else if (scene === "influencer_remix") {
      if (!videoUrl || !productToFeature) return;
      config.video_url = videoUrl;
      config.product_catalog = {
        products: [{
          name: productToFeature,
          usps,
          usage_scenario: usageScenario,
          pain_points: painPoints.split("\n").filter(Boolean),
          target_audience: productTargetAudience,
          competitor_context: competitorContext.split("\n").filter(Boolean),
        }],
      };
      config.influencer_name = influencerName || "";
      config.keep_original_audio = keepOriginalAudio;
      config.brand_guidelines = { brand_name: "", tone_of_voice: {} };
      config.storyboard_grid = "12";
      config.transition_style = "match_cut";
      config.continuity_mode = continuityMode === "high_quality" ? "high_quality" : "standard";
    } else if (scene === "brand_vlog") {
      const brand = VLOG_BRANDS.find(b => b.id === vlogBrandId);
      const productSku = brand?.products.find(p => p.id === vlogProductId);
      const models = VLOG_MODELS.filter(m => vlogModelIds.includes(m.id));
      const duration = VLOG_DURATION_OPTIONS.find(d => d.id === vlogDurationId);
      config.content_scenario = "brand_vlog";
      config.brand_id = vlogBrandId;
      config.product_sku = productSku || {};
      config.scene_id = vlogSceneId;
      config.selected_models = models;
      config.story_description = vlogStory;
      config.video_duration = duration?.seconds || 30;
      config.storyboard_grid = "12";
      config.transition_style = "soft_crossfade";
      config.continuity_mode = continuityMode === "high_quality" ? "high_quality" : "standard";
    }

    onSubmit(config);
  };

  const togglePlatform = (id: string) => {
    setSelectedPlatforms((prev) =>
      prev.includes(id) ? prev.filter((p) => p !== id) : [...prev, id]
    );
  };

  const canSubmit = () => {
    if (scene === "product_direct") return !!productName;
    if (scene === "brand_campaign") return !!brandPackage;
    if (scene === "influencer_remix") return !!videoUrl && !!productToFeature;
    if (scene === "brand_vlog") return !!vlogBrandId && !!vlogProductId;
    return false;
  };

  return (
    <div className="space-y-3">
      {/* GuidedForm (v2.0) */}
      {USE_GUIDED_FORM ? (
        <GuidedForm scene={scene} onSubmit={onSubmit} loading={loading} fieldErrors={fieldErrors} />
      ) : (
        /* Legacy form (only rendered when GuidedForm is disabled) */
        <div data-legacy-form>
        {/* Scene-specific fields */}
      {scene === "product_direct" && (
        <div className="space-y-3">
          {/* S1: Product Direct */}
          <div className="apple-card p-3 space-y-2">
            <h3 className="text-[12px] font-semibold text-[var(--text-body)] uppercase tracking-wider">
              <Package size={16} weight="fill" className="inline-block align-middle mr-1.5 text-[var(--fortune-red)]" />
              {t("scene.product_direct.title")}
            </h3>
            <div>
              <label className="block text-[12px] font-medium text-[var(--text-body)] mb-1">
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
              <label className="block text-[12px] font-medium text-[var(--text-body)] mb-1">
                {t("sceneForm.brandOptional")}
              </label>
              <input
                type="text"
                value={brandName}
                onChange={(e) => setBrandName(e.target.value)}
                placeholder={t("sceneForm.brandInputPlaceholder")}
                className="apple-input text-sm"
              />
            </div>
            <div>
              <label className="block text-[12px] font-medium text-[var(--text-body)] mb-1">
                {t("sceneForm.keyFeatures")}
              </label>
              <textarea
                value={keyFeatures}
                onChange={(e) => setKeyFeatures(e.target.value)}
                placeholder={t("sceneForm.keyFeaturesPlaceholder")}
                className="apple-input resize-none text-sm"
                rows={3}
              />
              <p className="text-[12px] text-[var(--text-muted)] mt-0.5">{t("sceneForm.keyFeaturesHint")}</p>
            </div>
            <div>
              <label className="block text-[12px] font-medium text-[var(--text-body)] mb-1">
                {t("sceneForm.category")}
              </label>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="apple-input text-sm"
              >
                <option value="">{t("sceneForm.categoryPlaceholder")}</option>
                {CATEGORIES.map((cat) => (
                  <option key={cat} value={cat}>
                    {t(`sceneForm.category${cat}`)}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-[12px] font-medium text-[var(--text-body)] mb-1">
                {t("continuity.label")}
              </label>
              <select
                value={continuityMode}
                onChange={(e) => setContinuityMode(e.target.value)}
                className="apple-input text-sm"
              >
                <option value="standard">{t("continuity.standard")}</option>
                <option value="high_quality">{t("continuity.highQuality")}</option>
              </select>
              <p className="text-[12px] text-[var(--text-muted)] mt-0.5">
                {continuityMode === "high_quality"
                  ? t("continuity.highQualityDesc")
                  : t("continuity.standardDesc")}
              </p>
            </div>

            {/* Product Details (expandable) */}
            <div className="border-t border-[var(--border-default)] pt-2 mt-2">
              <button
                type="button"
                onClick={() => setShowProductDetails(!showProductDetails)}
                className="flex items-center gap-1 text-[12px] font-medium text-[var(--text-body)] hover:text-[var(--text-h1)] transition-colors w-full"
              >
                <span>{showProductDetails ? "▾" : "▸"}</span>
                {t("product.detailsTitle")}
                <span className="text-[12px] text-[var(--text-muted)] ml-1">({t("product.detailsHint")})</span>
              </button>

              {showProductDetails && (
                <div className="space-y-2 mt-2">
                  {/* Usage Scenario */}
                  <div>
                    <label className="block text-[12px] font-medium text-[var(--text-body)] mb-1">
                      {t("product.usageScenario")}
                    </label>
                    <textarea
                      value={usageScenario}
                      onChange={(e) => setUsageScenario(e.target.value)}
                      placeholder={t("product.usageScenarioPlaceholder")}
                      className="apple-input resize-none text-xs"
                      rows={2}
                    />
                  </div>

                  {/* Pain Points */}
                  <div>
                    <label className="block text-[12px] font-medium text-[var(--text-body)] mb-1">
                      {t("product.painPoints")} <span className="text-[var(--text-muted)] font-normal">({t("product.painPointsHint")})</span>
                    </label>
                    <textarea
                      value={painPoints}
                      onChange={(e) => setPainPoints(e.target.value)}
                      placeholder={t("product.painPointsPlaceholder")}
                      className="apple-input resize-none text-xs"
                      rows={2}
                    />
                  </div>

                  {/* Target Audience */}
                  <div>
                    <label className="block text-[12px] font-medium text-[var(--text-body)] mb-1">
                      {t("product.targetAudience")}
                    </label>
                    <textarea
                      value={productTargetAudience}
                      onChange={(e) => setProductTargetAudience(e.target.value)}
                      placeholder={t("product.targetAudiencePlaceholder")}
                      className="apple-input resize-none text-xs"
                      rows={2}
                    />
                  </div>

                  {/* Competitor Context */}
                  <div>
                    <label className="block text-[12px] font-medium text-[var(--text-body)] mb-1">
                      {t("product.competitorContext")}
                    </label>
                    <textarea
                      value={competitorContext}
                      onChange={(e) => setCompetitorContext(e.target.value)}
                      placeholder={t("product.competitorContextPlaceholder")}
                      className="apple-input resize-none text-xs"
                      rows={2}
                    />
                  </div>
                </div>
              )}
            </div>

            {/* Brand Voice (expandable) */}
            <div className="border-t border-[var(--border-default)] pt-2 mt-2">
              <button
                type="button"
                onClick={() => setShowBrandVoice(!showBrandVoice)}
                className="flex items-center gap-1 text-[12px] font-medium text-[var(--text-body)] hover:text-[var(--text-h1)] transition-colors w-full"
              >
                <span>{showBrandVoice ? "▾" : "▸"}</span>
                {t("brand.voiceTitle")}
              </button>

              {showBrandVoice && (
                <div className="space-y-2 mt-2">
                  <div>
                    <label className="block text-[12px] font-medium text-[var(--text-body)] mb-1">
                      {t("brand.voiceDo")}
                    </label>
                    <textarea
                      value={brandVoiceDo}
                      onChange={(e) => setBrandVoiceDo(e.target.value)}
                      placeholder={t("brand.voiceDoPlaceholder")}
                      className="apple-input resize-none text-xs"
                      rows={3}
                    />
                  </div>
                  <div>
                    <label className="block text-[12px] font-medium text-[var(--text-body)] mb-1">
                      {t("brand.voiceDont")}
                    </label>
                    <textarea
                      value={brandVoiceDont}
                      onChange={(e) => setBrandVoiceDont(e.target.value)}
                      placeholder={t("brand.voiceDontPlaceholder")}
                      className="apple-input resize-none text-xs"
                      rows={3}
                    />
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {scene === "brand_campaign" && (
        <div className="space-y-3">
          {/* S2: Brand Campaign */}
          <div className="apple-card p-3 space-y-2">
            <h3 className="text-[12px] font-semibold text-[var(--text-body)] uppercase tracking-wider">
              <Megaphone size={16} weight="fill" className="inline-block align-middle mr-1.5 text-[var(--fortune-red)]" />
              {t("scene.brand_campaign.title")}
            </h3>
            <div>
              <label className="block text-[12px] font-medium text-[var(--text-body)] mb-1">
                {t("sceneForm.brandPackageRequired")}
              </label>
              <div className="flex gap-2">
                <select
                  value={brandPackage}
                  onChange={(e) => setBrandPackage(e.target.value)}
                  className="apple-input text-sm flex-1"
                >
                  <option value="">{t("sceneForm.categoryPlaceholder")}</option>
                  {BRAND_PACKAGES.map((bp) => (
                    <option key={bp.id} value={bp.id}>
                      {t(bp.nameKey)}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  className="text-[12px] text-[var(--fortune-red)] bg-[rgba(215,92,112,0.05)] px-2 py-1 rounded-lg border border-[rgba(215,92,112,0.18)] hover:bg-[rgba(215,92,112,0.10)] transition-colors cursor-pointer whitespace-nowrap"
                >
                  {t("sceneForm.brandPackageNew")}
                </button>
              </div>
            </div>
            <div>
              <label className="block text-[12px] font-medium text-[var(--text-body)] mb-1">
                {t("sceneForm.campaignTheme")}
              </label>
              <input
                type="text"
                value={campaignTheme}
                onChange={(e) => setCampaignTheme(e.target.value)}
                placeholder={t("sceneForm.campaignThemePlaceholder")}
                className="apple-input text-sm"
              />
            </div>
            <div>
              <label className="block text-[12px] font-medium text-[var(--text-body)] mb-1">
                {t("sceneForm.keyMessage")}
              </label>
              <textarea
                value={keyMessage}
                onChange={(e) => setKeyMessage(e.target.value)}
                placeholder={t("sceneForm.keyMessage")}
                className="apple-input resize-none text-sm"
                rows={2}
              />
            </div>
            <div>
              <label className="block text-[12px] font-medium text-[var(--text-body)] mb-1">
                {t("sceneForm.targetAudience")}
              </label>
              <input
                type="text"
                value={brandTargetAudience}
                onChange={(e) => setBrandTargetAudience(e.target.value)}
                placeholder={t("sceneForm.targetAudience")}
                className="apple-input text-sm"
              />
            </div>

            {/* Campaign Details (expandable) */}
            <div className="border-t border-[var(--border-default)] pt-2 mt-2">
              <button
                type="button"
                onClick={() => setShowCampaignDetails(!showCampaignDetails)}
                className="flex items-center gap-1 text-[12px] font-medium text-[var(--text-body)] hover:text-[var(--text-h1)] transition-colors w-full"
              >
                <span>{showCampaignDetails ? "▾" : "▸"}</span>
                {t("campaign.detailsTitle")}
                <span className="text-[12px] text-[var(--text-muted)] ml-1">({t("campaign.detailsHint")})</span>
              </button>

              {showCampaignDetails && (
                <div className="space-y-2 mt-2">
                  {/* Campaign Goal */}
                  <div>
                    <label className="block text-[12px] font-medium text-[var(--text-body)] mb-1">
                      {t("campaign.goal")}
                    </label>
                    <textarea
                      value={campaignGoal}
                      onChange={(e) => setCampaignGoal(e.target.value)}
                      placeholder={t("campaign.goalPlaceholder")}
                      className="apple-input resize-none text-xs"
                      rows={2}
                    />
                  </div>

                  {/* Brand Values */}
                  <div>
                    <label className="block text-[12px] font-medium text-[var(--text-body)] mb-1">
                      {t("campaign.values")}
                    </label>
                    <textarea
                      value={brandValues}
                      onChange={(e) => setBrandValues(e.target.value)}
                      placeholder={t("campaign.valuesPlaceholder")}
                      className="apple-input resize-none text-xs"
                      rows={2}
                    />
                  </div>

                  {/* Visual Identity */}
                  <div>
                    <label className="block text-[12px] font-medium text-[var(--text-body)] mb-1">
                      {t("campaign.visualIdentity")}
                    </label>
                    <textarea
                      value={visualIdentity}
                      onChange={(e) => setVisualIdentity(e.target.value)}
                      placeholder={t("campaign.visualIdentityPlaceholder")}
                      className="apple-input resize-none text-xs"
                      rows={2}
                    />
                  </div>

                  {/* Competitor Campaigns */}
                  <div>
                    <label className="block text-[12px] font-medium text-[var(--text-body)] mb-1">
                      {t("campaign.competitorCampaigns")}
                    </label>
                    <textarea
                      value={competitorCampaigns}
                      onChange={(e) => setCompetitorCampaigns(e.target.value)}
                      placeholder={t("campaign.competitorCampaignsPlaceholder")}
                      className="apple-input resize-none text-xs"
                      rows={2}
                    />
                  </div>
                </div>
              )}
            </div>
            {/* Continuity Mode */}
            <div>
              <label className="block text-[12px] font-medium text-[var(--text-body)] mb-1">
                {t("continuity.label")}
              </label>
              <select
                value={continuityMode}
                onChange={(e) => setContinuityMode(e.target.value)}
                className="apple-input text-sm"
              >
                <option value="standard">{t("continuity.standard")}</option>
                <option value="high_quality">{t("continuity.highQuality")}</option>
              </select>
              <p className="text-[12px] text-[var(--text-muted)] mt-0.5">
                {continuityMode === "high_quality"
                  ? t("continuity.highQualityDesc")
                  : t("continuity.standardDesc")}
              </p>
            </div>
          </div>
        </div>
      )}

      {scene === "influencer_remix" && (
        <div className="space-y-3">
          {/* S3: Influencer Remix */}
          <div className="apple-card p-3 space-y-2">
            <h3 className="text-[12px] font-semibold text-[var(--text-body)] uppercase tracking-wider">
              <Users size={16} weight="fill" className="inline-block align-middle mr-1.5 text-[var(--fortune-red)]" />
              {t("scene.influencer_remix.title")}
            </h3>
            <div>
              <label className="block text-[12px] font-medium text-[var(--text-body)] mb-1">
                {t("sceneForm.videoUrl")} *
              </label>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={videoUrl}
                  onChange={(e) => setVideoUrl(e.target.value)}
                  placeholder={t("sceneForm.videoUrlPlaceholder")}
                  className="apple-input text-sm flex-1"
                />
                <button
                  type="button"
                  className="text-[12px] text-[var(--fortune-red)] bg-[rgba(215,92,112,0.05)] px-2 py-1 rounded-lg border border-[rgba(215,92,112,0.18)] hover:bg-[rgba(215,92,112,0.10)] transition-colors cursor-pointer whitespace-nowrap"
                >
                  {t("sceneForm.orUpload")}
                </button>
              </div>
            </div>
            <div>
              <label className="block text-[12px] font-medium text-[var(--text-body)] mb-1">
                {t("sceneForm.productToFeatureRequired")}
              </label>
              <input
                type="text"
                value={productToFeature}
                onChange={(e) => setProductToFeature(e.target.value)}
                placeholder={t("sceneForm.productToFeature")}
                className="apple-input text-sm"
              />
            </div>
            <div>
              <label className="block text-[12px] font-medium text-[var(--text-body)] mb-1">
                {t("sceneForm.influencerName")}
              </label>
              <input
                type="text"
                value={influencerName}
                onChange={(e) => setInfluencerName(e.target.value)}
                placeholder={t("sceneForm.influencerName")}
                className="apple-input text-sm"
              />
            </div>
            <div className="flex items-center gap-2 pt-1">
              <input
                type="checkbox"
                id="keep-original-audio"
                checked={keepOriginalAudio}
                onChange={(e) => setKeepOriginalAudio(e.target.checked)}
                className="w-3.5 h-3.5 accent-[var(--fortune-red)]"
              />
              <label htmlFor="keep-original-audio" className="text-[12px] font-medium text-[var(--text-body)] cursor-pointer">
                {t("sceneForm.keepOriginalAudio")}
              </label>
            </div>
            <div>
              <label className="block text-[12px] font-medium text-[var(--text-body)] mb-1">
                {t("continuity.label")}
              </label>
              <select
                value={continuityMode}
                onChange={(e) => setContinuityMode(e.target.value)}
                className="apple-input text-sm"
              >
                <option value="standard">{t("continuity.standard")}</option>
                <option value="high_quality">{t("continuity.highQuality")}</option>
              </select>
              <p className="text-[12px] text-[var(--text-muted)] mt-0.5">
                {continuityMode === "high_quality"
                  ? t("continuity.highQualityDesc")
                  : t("continuity.standardDesc")}
              </p>
            </div>

            {/* Product Details (expandable) — reused from S1 */}
            <div className="border-t border-[var(--border-default)] pt-2 mt-2">
              <button
                type="button"
                onClick={() => setShowProductDetails(!showProductDetails)}
                className="flex items-center gap-1 text-[12px] font-medium text-[var(--text-body)] hover:text-[var(--text-h1)] transition-colors w-full"
              >
                <span>{showProductDetails ? "▾" : "▸"}</span>
                {t("product.detailsTitle")}
                <span className="text-[12px] text-[var(--text-muted)] ml-1">({t("product.detailsHint")})</span>
              </button>

              {showProductDetails && (
                <div className="space-y-2 mt-2">
                  {/* Usage Scenario */}
                  <div>
                    <label className="block text-[12px] font-medium text-[var(--text-body)] mb-1">
                      {t("product.usageScenario")}
                    </label>
                    <textarea
                      value={usageScenario}
                      onChange={(e) => setUsageScenario(e.target.value)}
                      placeholder={t("product.usageScenarioPlaceholder")}
                      className="apple-input resize-none text-xs"
                      rows={2}
                    />
                  </div>

                  {/* Pain Points */}
                  <div>
                    <label className="block text-[12px] font-medium text-[var(--text-body)] mb-1">
                      {t("product.painPoints")} <span className="text-[var(--text-muted)] font-normal">({t("product.painPointsHint")})</span>
                    </label>
                    <textarea
                      value={painPoints}
                      onChange={(e) => setPainPoints(e.target.value)}
                      placeholder={t("product.painPointsPlaceholder")}
                      className="apple-input resize-none text-xs"
                      rows={2}
                    />
                  </div>

                  {/* Target Audience */}
                  <div>
                    <label className="block text-[12px] font-medium text-[var(--text-body)] mb-1">
                      {t("product.targetAudience")}
                    </label>
                    <textarea
                      value={productTargetAudience}
                      onChange={(e) => setProductTargetAudience(e.target.value)}
                      placeholder={t("product.targetAudiencePlaceholder")}
                      className="apple-input resize-none text-xs"
                      rows={2}
                    />
                  </div>

                  {/* Competitor Context */}
                  <div>
                    <label className="block text-[12px] font-medium text-[var(--text-body)] mb-1">
                      {t("product.competitorContext")}
                    </label>
                    <textarea
                      value={competitorContext}
                      onChange={(e) => setCompetitorContext(e.target.value)}
                      placeholder={t("product.competitorContextPlaceholder")}
                      className="apple-input resize-none text-xs"
                      rows={2}
                    />
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Brand VLOG Scene ── */}
      {scene === "brand_vlog" && (
        <div className="space-y-3">
          <div className="apple-card p-3 space-y-2">
            <h3 className="text-[12px] font-semibold text-[var(--text-body)] uppercase tracking-wider">
              <Camera size={16} weight="fill" className="inline-block align-middle mr-1.5 text-[var(--fortune-red)]" />
              {t("scene.brand_vlog.title")}
            </h3>
            {/* Brand + Product SKU */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-[12px] font-medium text-[var(--text-body)] mb-1">{t("vlog.brandLabel")}</label>
                <select
                  value={vlogBrandId}
                  onChange={(e) => { setVlogBrandId(e.target.value); const brand = VLOG_BRANDS.find(b => b.id === e.target.value); if (brand?.products?.[0]) setVlogProductId(brand.products[0].id); }}
                  className="apple-input text-sm"
                >
                  {VLOG_BRANDS.map(b => <option key={b.id} value={b.id}>{b.name} · {b.tone}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-[12px] font-medium text-[var(--text-body)] mb-1">{t("vlog.productSku")}</label>
                <select value={vlogProductId} onChange={(e) => setVlogProductId(e.target.value)} className="apple-input text-sm">
                  {(VLOG_BRANDS.find(b => b.id === vlogBrandId)?.products || []).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
                <p className="text-[12px] text-[var(--text-muted)] mt-0.5">{t("vlog.productSkuHint")}</p>
              </div>
            </div>

            {/* Scene Selection */}
            <div>
              <label className="block text-[12px] font-medium text-[var(--text-body)] mb-2">{t("vlog.scene")}</label>
              <div className="grid grid-cols-3 gap-2">
                {VLOG_SCENES.map(s => (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => setVlogSceneId(s.id)}
                    className={`text-left px-3 py-2.5 rounded-lg border transition-all cursor-pointer ${
                      vlogSceneId === s.id
                        ? "border-[var(--color-accent)] bg-[var(--color-accent)]/5 ring-1 ring-[var(--color-accent)]/20"
                        : "border-[var(--border-default)] bg-[var(--bg-card)] hover:border-[var(--border-default)]"
                    }`}
                  >
                    <div className="text-xs font-semibold text-[var(--color-text-primary)]">{s.name}</div>
                    <div className="text-[12px] text-[var(--color-text-tertiary)] mt-0.5">{s.desc}</div>
                  </button>
                ))}
              </div>
            </div>

            {/* Six-View */}
            <div>
              <label className="block text-[12px] font-medium text-[var(--text-body)] mb-2">{t("vlog.views")}</label>
              {VLOG_BRANDS.find(b => b.id === vlogBrandId)?.products.find(p => p.id === vlogProductId)?.views && (
                <VlogSixView views={VLOG_BRANDS.find(b => b.id === vlogBrandId)!.products.find(p => p.id === vlogProductId)!.views} />
              )}
            </div>

            {/* Model Selection */}
            <div>
              <label className="block text-[12px] font-medium text-[var(--text-body)] mb-2">{t("vlog.models")} · {t("vlog.modelsHint")}</label>
              <VlogModelSelector
                models={VLOG_MODELS}
                selected={vlogModelIds}
                onChange={setVlogModelIds}
              />
            </div>

            {/* Story Description */}
            <div>
              <label className="block text-[12px] font-medium text-[var(--text-body)] mb-1">{t("vlog.story")}</label>
              <textarea
                value={vlogStory}
                onChange={(e) => setVlogStory(e.target.value.slice(0, 300))}
                placeholder={t("vlog.storyPlaceholder")}
                className="apple-input resize-none text-sm"
                rows={4}
                maxLength={300}
              />
              <div className="flex justify-between mt-1">
                <span className="text-[12px] text-[var(--text-muted)]">{t("vlog.storyHint")}</span>
                <span className="text-[12px] text-[var(--text-muted)]">{vlogStory.length} / 300</span>
              </div>
            </div>

            {/* Duration */}
            <div>
              <label className="block text-[12px] font-medium text-[var(--text-body)] mb-2">{t("vlog.duration")}</label>
              <div className="flex gap-2">
                {VLOG_DURATION_OPTIONS.map(d => (
                  <button
                    key={d.id}
                    type="button"
                    onClick={() => setVlogDurationId(d.id)}
                    className={`flex-1 py-2.5 rounded-xl text-xs font-medium transition-all cursor-pointer ${
                      vlogDurationId === d.id
                        ? "bg-[var(--color-accent)] text-white shadow-sm"
                        : "bg-[var(--color-bg)] text-[var(--color-text-secondary)] border border-[var(--color-border-light)] hover:border-[var(--color-border)]"
                    }`}
                  >
                    <div>{d.label}</div>
                    <div className="text-[12px] opacity-60 mt-0.5">{d.note}</div>
                  </button>
                ))}
              </div>
            </div>

            {/* Continuity Mode */}
            <div>
              <label className="block text-[12px] font-medium text-[var(--text-body)] mb-1">
                {t("continuity.label")}
              </label>
              <select
                value={continuityMode}
                onChange={(e) => setContinuityMode(e.target.value)}
                className="apple-input text-sm"
              >
                <option value="standard">{t("continuity.standard")}</option>
                <option value="high_quality">{t("continuity.highQuality")}</option>
              </select>
              <p className="text-[12px] text-[var(--text-muted)] mt-0.5">
                {continuityMode === "high_quality"
                  ? t("continuity.highQualityDesc")
                  : t("continuity.standardDesc")}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Shared footer: Advanced + Submit */}
      <div className="space-y-2">
        {/* Advanced section */}
        <div className="apple-card p-3">
          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="flex items-center justify-between w-full cursor-pointer"
          >
            <span className="text-[12px] font-semibold text-[var(--text-body)] uppercase tracking-wider">
              {t("sceneForm.advanced")}
            </span>
            <svg
              width="12"
              height="12"
              viewBox="0 0 12 12"
              fill="none"
              className={`transition-transform duration-200 ${showAdvanced ? "rotate-180" : ""}`}
            >
              <path d="M3 4.5L6 7.5L9 4.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
          {showAdvanced && (
            <div className="mt-3 space-y-3 pt-3 border-t border-[var(--border-default)]">
              {/* Platform checkboxes */}
              <div>
                <label className="block text-[12px] font-medium text-[var(--text-body)] mb-1.5 uppercase tracking-wider">
                  {t("distPlatform")}
                </label>
                <div className="flex flex-wrap gap-1.5">
                  {Object.keys(PLATFORM_LABELS).map((id) => {
                    const active = selectedPlatforms.includes(id);
                    return (
                      <button
                        key={id}
                        type="button"
                        onClick={() => togglePlatform(id)}
                        className={`apple-pill text-xs py-1 px-2.5 ${active ? "active" : ""}`}
                      >
                        {React.createElement(PLATFORM_ICON_MAP[id] || ShoppingBag, { size: 12, weight: "fill" })}
                        {t("platform." + id)}
                      </button>
                    );
                  })}
                </div>
              </div>
              {/* Mode toggle */}
              <div>
                <label className="block text-[12px] font-medium text-[var(--text-body)] mb-1.5 uppercase tracking-wider">
                  {t("sceneForm.modeExpert")}/{t("sceneForm.modeSmart")}
                </label>
                <div className="flex gap-1.5">
                  <button
                    type="button"
                    onClick={() => setMode("expert")}
                    className={`text-[12px] px-2.5 py-1 rounded-full font-medium transition-all cursor-pointer ${
                      mode === "expert"
                        ? "bg-[var(--fortune-red)] text-white"
                        : "bg-[var(--bg-panel)] text-[var(--text-body)] hover:bg-[var(--border-default)]"
                    }`}
                  >
                    {t("sceneForm.modeExpert")}
                  </button>
                  <button
                    type="button"
                    onClick={() => setMode("smart")}
                    className={`text-[12px] px-2.5 py-1 rounded-full font-medium transition-all cursor-pointer ${
                      mode === "smart"
                        ? "bg-[var(--cinema-azure)] text-white"
                        : "bg-[var(--bg-panel)] text-[var(--text-body)] hover:bg-[var(--border-default)]"
                    }`}
                  >
                    {t("sceneForm.modeSmart")}
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Submit button */}
        <button
          type="button"
          onClick={handleSubmit}
          disabled={loading || !canSubmit()}
          className="apple-btn apple-btn-primary w-full py-2.5 text-sm"
        >
          {loading ? (
            <span className="flex items-center gap-2">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" className="animate-spin">
                <circle cx="12" cy="12" r="10" stroke="rgba(255,255,255,0.3)" strokeWidth="3" />
                <path d="M12 2a10 10 0 0 1 10 10" stroke="white" strokeWidth="3" strokeLinecap="round" />
              </svg>
              {t("common.loading")}
            </span>
          ) : (
            <>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                <polygon points="7,5 19,12 7,19" fill="white" />
              </svg>
              {t("sceneForm.continue")}
            </>
          )}
        </button>
      </div>
      </div>{/* /legacy form */}
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
      </div>
      )}
