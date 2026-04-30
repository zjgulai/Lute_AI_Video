"use client";

import React, { useState } from "react";
import { Users, Megaphone, Package, ShoppingBag, Music, MessageCircle, Video, ShoppingCart, ExternalLink } from "lucide-react";
import { PLATFORM_LABELS, CONTENT_SCENARIOS } from "./types";
import { useI18n } from "@/i18n/I18nProvider";

interface Props {
  scene: string;
  onSubmit: (config: any) => void;
  loading: boolean;
}

const CATEGORIES = ["Home", "Baby", "Electronics", "Health", "Fashion", "Other"];

const BRAND_PACKAGES = [
  { id: "bp_default", nameKey: "brand.packageName" },
];

const PLATFORM_ICON_MAP: Record<string, React.ComponentType<{ size?: number; strokeWidth?: number; className?: string }>> = {
  shopify: ShoppingBag,
  amazon: ShoppingCart,
  tiktok: Music,
  reddit: MessageCircle,
  facebook: ExternalLink,
  youtube_shorts: Video,
};

const SCENE_ICON_MAP: Record<string, React.ComponentType<{ size?: number; strokeWidth?: number; className?: string }>> = {
  product_direct: Package,
  brand_campaign: Megaphone,
  influencer_remix: Users,
};

export default function SceneForm({ scene, onSubmit, loading }: Props) {
  const { t } = useI18n();
  const [mode, setMode] = useState<"expert" | "smart">("expert");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [showProductDetails, setShowProductDetails] = useState(false);

  // S1 fields
  const [productName, setProductName] = useState("Trunk Baby Organizer");
  const [brandName, setBrandName] = useState("Momcozy");
  const [keyFeatures, setKeyFeatures] = useState("Quick-grab access, no digging through trunk\n5 clear compartments for diapers, wipes, snacks, clothes, toys\nStays stable in car, no rolling or tipping\nCollapsible when not in use\nBoth parents can find everything instantly");
  const [category, setCategory] = useState("Baby");

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

    let config: any = {
      content_scenario: scene,
      target_platforms: selectedPlatforms,
      target_languages: ["en"],
      content_calendar_week: getCurrentWeek(),
      mode,
    };

    if (scene === "product_direct") {
      if (!productName) return;
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
    return false;
  };

  return (
    <div className="space-y-3">
      {/* Scene-specific fields */}
      {scene === "product_direct" && (
        <div className="space-y-3">
          {/* S1: Product Direct */}
          <div className="apple-card p-3 space-y-2">
            <h3 className="text-[11px] font-semibold text-[#86868b] uppercase tracking-wider">
              <Package size={16} strokeWidth={1.5} className="inline-block align-middle mr-1.5 text-[#7CB342]" />
              {t("scene.product_direct.title")}
            </h3>
            <div>
              <label className="block text-[11px] font-medium text-[#86868b] mb-1">
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
              <label className="block text-[11px] font-medium text-[#86868b] mb-1">
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
              <label className="block text-[11px] font-medium text-[#86868b] mb-1">
                {t("sceneForm.keyFeatures")}
              </label>
              <textarea
                value={keyFeatures}
                onChange={(e) => setKeyFeatures(e.target.value)}
                placeholder={t("sceneForm.keyFeaturesPlaceholder")}
                className="apple-input resize-none text-sm"
                rows={3}
              />
              <p className="text-[10px] text-[#aeaeb2] mt-0.5">{t("sceneForm.keyFeaturesHint")}</p>
            </div>
            <div>
              <label className="block text-[11px] font-medium text-[#86868b] mb-1">
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

            {/* Product Details (expandable) */}
            <div className="border-t border-[#e8e8ed] pt-2 mt-2">
              <button
                type="button"
                onClick={() => setShowProductDetails(!showProductDetails)}
                className="flex items-center gap-1 text-[11px] font-medium text-[#86868b] hover:text-[#1d1d1f] transition-colors w-full"
              >
                <span>{showProductDetails ? "▾" : "▸"}</span>
                {t("product.detailsTitle")}
                <span className="text-[9px] text-[#aeaeb2] ml-1">({t("product.detailsHint")})</span>
              </button>

              {showProductDetails && (
                <div className="space-y-2 mt-2">
                  {/* Usage Scenario */}
                  <div>
                    <label className="block text-[11px] font-medium text-[#86868b] mb-1">
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
                    <label className="block text-[11px] font-medium text-[#86868b] mb-1">
                      {t("product.painPoints")} <span className="text-[#aeaeb2] font-normal">({t("product.painPointsHint")})</span>
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
                    <label className="block text-[11px] font-medium text-[#86868b] mb-1">
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
                    <label className="block text-[11px] font-medium text-[#86868b] mb-1">
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
            <div className="border-t border-[#e8e8ed] pt-2 mt-2">
              <button
                type="button"
                onClick={() => setShowBrandVoice(!showBrandVoice)}
                className="flex items-center gap-1 text-[11px] font-medium text-[#86868b] hover:text-[#1d1d1f] transition-colors w-full"
              >
                <span>{showBrandVoice ? "▾" : "▸"}</span>
                {t("brand.voiceTitle")}
              </button>

              {showBrandVoice && (
                <div className="space-y-2 mt-2">
                  <div>
                    <label className="block text-[11px] font-medium text-[#86868b] mb-1">
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
                    <label className="block text-[11px] font-medium text-[#86868b] mb-1">
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
            <h3 className="text-[11px] font-semibold text-[#86868b] uppercase tracking-wider">
              <Megaphone size={16} strokeWidth={1.5} className="inline-block align-middle mr-1.5 text-[#7CB342]" />
              {t("scene.brand_campaign.title")}
            </h3>
            <div>
              <label className="block text-[11px] font-medium text-[#86868b] mb-1">
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
                  className="text-[10px] text-[#7CB342] bg-[#7CB342]/5 px-2 py-1 rounded-lg border border-[#7CB342]/20 hover:bg-[#7CB342]/10 transition-colors cursor-pointer whitespace-nowrap"
                >
                  {t("sceneForm.brandPackageNew")}
                </button>
              </div>
            </div>
            <div>
              <label className="block text-[11px] font-medium text-[#86868b] mb-1">
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
              <label className="block text-[11px] font-medium text-[#86868b] mb-1">
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
              <label className="block text-[11px] font-medium text-[#86868b] mb-1">
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
            <div className="border-t border-[#e8e8ed] pt-2 mt-2">
              <button
                type="button"
                onClick={() => setShowCampaignDetails(!showCampaignDetails)}
                className="flex items-center gap-1 text-[11px] font-medium text-[#86868b] hover:text-[#1d1d1f] transition-colors w-full"
              >
                <span>{showCampaignDetails ? "▾" : "▸"}</span>
                {t("campaign.detailsTitle")}
                <span className="text-[9px] text-[#aeaeb2] ml-1">({t("campaign.detailsHint")})</span>
              </button>

              {showCampaignDetails && (
                <div className="space-y-2 mt-2">
                  {/* Campaign Goal */}
                  <div>
                    <label className="block text-[11px] font-medium text-[#86868b] mb-1">
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
                    <label className="block text-[11px] font-medium text-[#86868b] mb-1">
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
                    <label className="block text-[11px] font-medium text-[#86868b] mb-1">
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
                    <label className="block text-[11px] font-medium text-[#86868b] mb-1">
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
          </div>
        </div>
      )}

      {scene === "influencer_remix" && (
        <div className="space-y-3">
          {/* S3: Influencer Remix */}
          <div className="apple-card p-3 space-y-2">
            <h3 className="text-[11px] font-semibold text-[#86868b] uppercase tracking-wider">
              <Users size={16} strokeWidth={1.5} className="inline-block align-middle mr-1.5 text-[#7CB342]" />
              {t("scene.influencer_remix.title")}
            </h3>
            <div>
              <label className="block text-[11px] font-medium text-[#86868b] mb-1">
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
                  className="text-[10px] text-[#7CB342] bg-[#7CB342]/5 px-2 py-1 rounded-lg border border-[#7CB342]/20 hover:bg-[#7CB342]/10 transition-colors cursor-pointer whitespace-nowrap"
                >
                  {t("sceneForm.orUpload")}
                </button>
              </div>
            </div>
            <div>
              <label className="block text-[11px] font-medium text-[#86868b] mb-1">
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
              <label className="block text-[11px] font-medium text-[#86868b] mb-1">
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
                className="w-3.5 h-3.5 accent-[#7CB342]"
              />
              <label htmlFor="keep-original-audio" className="text-[11px] font-medium text-[#86868b] cursor-pointer">
                {t("sceneForm.keepOriginalAudio")}
              </label>
            </div>

            {/* Product Details (expandable) — reused from S1 */}
            <div className="border-t border-[#e8e8ed] pt-2 mt-2">
              <button
                type="button"
                onClick={() => setShowProductDetails(!showProductDetails)}
                className="flex items-center gap-1 text-[11px] font-medium text-[#86868b] hover:text-[#1d1d1f] transition-colors w-full"
              >
                <span>{showProductDetails ? "▾" : "▸"}</span>
                {t("product.detailsTitle")}
                <span className="text-[9px] text-[#aeaeb2] ml-1">({t("product.detailsHint")})</span>
              </button>

              {showProductDetails && (
                <div className="space-y-2 mt-2">
                  {/* Usage Scenario */}
                  <div>
                    <label className="block text-[11px] font-medium text-[#86868b] mb-1">
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
                    <label className="block text-[11px] font-medium text-[#86868b] mb-1">
                      {t("product.painPoints")} <span className="text-[#aeaeb2] font-normal">({t("product.painPointsHint")})</span>
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
                    <label className="block text-[11px] font-medium text-[#86868b] mb-1">
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
                    <label className="block text-[11px] font-medium text-[#86868b] mb-1">
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

      {/* Shared footer: Advanced + Submit */}
      <div className="space-y-2">
        {/* Advanced section */}
        <div className="apple-card p-3">
          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="flex items-center justify-between w-full cursor-pointer"
          >
            <span className="text-[11px] font-semibold text-[#86868b] uppercase tracking-wider">
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
            <div className="mt-3 space-y-3 pt-3 border-t border-[#e8e8ed]">
              {/* Platform checkboxes */}
              <div>
                <label className="block text-[10px] font-medium text-[#86868b] mb-1.5 uppercase tracking-wider">
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
                        {React.createElement(PLATFORM_ICON_MAP[id] || ShoppingBag, { size: 12, strokeWidth: 1.5 })}
                        {t("platform." + id)}
                      </button>
                    );
                  })}
                </div>
              </div>
              {/* Mode toggle */}
              <div>
                <label className="block text-[10px] font-medium text-[#86868b] mb-1.5 uppercase tracking-wider">
                  {t("sceneForm.modeExpert")}/{t("sceneForm.modeSmart")}
                </label>
                <div className="flex gap-1.5">
                  <button
                    type="button"
                    onClick={() => setMode("expert")}
                    className={`text-[9px] px-2.5 py-1 rounded-full font-medium transition-all cursor-pointer ${
                      mode === "expert"
                        ? "bg-[#7CB342] text-white"
                        : "bg-[#f5f5f7] text-[#86868b] hover:bg-[#e8e8ed]"
                    }`}
                  >
                    {t("sceneForm.modeExpert")}
                  </button>
                  <button
                    type="button"
                    onClick={() => setMode("smart")}
                    className={`text-[9px] px-2.5 py-1 rounded-full font-medium transition-all cursor-pointer ${
                      mode === "smart"
                        ? "bg-[#5B8DEF] text-white"
                        : "bg-[#f5f5f7] text-[#86868b] hover:bg-[#e8e8ed]"
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
