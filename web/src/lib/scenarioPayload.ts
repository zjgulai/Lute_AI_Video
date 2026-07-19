type UnknownRecord = Record<string, unknown>;

export type SceneSubmitConfig = UnknownRecord & {
  content_scenario?: string;
  product_catalog?: UnknownRecord & {
    name?: string;
    products?: Array<UnknownRecord & { name?: string; usps?: unknown }>;
    usps?: unknown;
  };
  product?: UnknownRecord;
  brand_package?: unknown;
  brand_guidelines?: UnknownRecord & { brand_name?: string };
  target_platforms?: string[];
  target_languages?: string[];
  content_calendar_week?: string;
  week?: string;
  video_duration?: number;
  campaign_theme?: string;
  key_message?: string;
  target_audience?: string;
  video_url?: string;
  influencer_name?: string;
  footage_assets?: unknown;
  product_info?: unknown;
  topic?: string;
  brand_id?: string;
  product_sku?: unknown;
  scene_id?: string;
  selected_models?: unknown;
  story_description?: string;
  product_views?: unknown;
  enable_media_synthesis?: boolean;
  artifact_disposition?: "pending_review" | "quarantine";
  provider_max_retries?: number;
};

export type GenerationSafetyIntent = {
  enable_media_synthesis: boolean;
  artifact_disposition: "pending_review" | "quarantine";
  provider_max_retries: 0;
};

export function normalizeGenerationSafetyIntent(
  config: Record<string, unknown>,
): GenerationSafetyIntent {
  return {
    enable_media_synthesis: config.enable_media_synthesis === true,
    artifact_disposition: config.artifact_disposition === "quarantine"
      ? "quarantine"
      : "pending_review",
    provider_max_retries: 0,
  };
}

export function withExplicitMediaGenerationIntent<T extends Record<string, unknown>>(
  payload: T,
): T & GenerationSafetyIntent {
  return {
    ...payload,
    enable_media_synthesis: true,
    artifact_disposition: "pending_review",
    provider_max_retries: 0,
  };
}

function asRecord(value: unknown): UnknownRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? value as UnknownRecord : {};
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function definedEntries(record: UnknownRecord): UnknownRecord {
  return Object.fromEntries(Object.entries(record).filter(([, value]) => value !== undefined));
}

function firstProduct(config: SceneSubmitConfig): UnknownRecord {
  const products = config.product_catalog?.products;
  if (Array.isArray(products) && products[0]) return products[0];
  return {};
}

function basePayload(config: SceneSubmitConfig, fallbackVideoDuration: number): UnknownRecord {
  return definedEntries({
    video_duration: config.video_duration || fallbackVideoDuration,
    ...normalizeGenerationSafetyIntent(config),
    commercial_injection_plan: config.commercial_injection_plan,
  });
}

function buildBrandPackage(config: SceneSubmitConfig): UnknownRecord {
  const rawPackage = asRecord(config.brand_package);
  const rawPackageName = typeof config.brand_package === "string" ? config.brand_package : "";
  const brandGuidelines = asRecord(config.brand_guidelines);
  const brandName =
    asString(rawPackage.brand_name)
    || rawPackageName
    || asString(brandGuidelines.brand_name)
    || "Momcozy";

  return definedEntries({
    ...rawPackage,
    brand_name: brandName,
    campaign_theme: config.campaign_theme,
    key_message: config.key_message,
    target_audience: config.target_audience,
    tone_of_voice: brandGuidelines.tone_of_voice,
    visual_identity: brandGuidelines.visual_identity,
    campaign_goal: brandGuidelines.campaign_goal,
    brand_values: brandGuidelines.brand_values,
    competitor_campaigns: brandGuidelines.competitor_campaigns,
  });
}

function buildS3Product(config: SceneSubmitConfig): UnknownRecord {
  const explicitProduct = asRecord(config.product);
  if (Object.keys(explicitProduct).length > 0) return explicitProduct;

  const product = firstProduct(config);
  return definedEntries({
    ...product,
    name: asString(product.name)
      || config.product_catalog?.name
      || "Product",
  });
}

function normalizeFootageAssets(value: unknown): Array<UnknownRecord> {
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        if (typeof item === "string" && item.trim()) {
          return { path: item.trim(), source: "guided_form" };
        }
        return asRecord(item);
      })
      .filter((item) => Object.keys(item).length > 0);
  }
  if (typeof value === "string" && value.trim()) {
    return [{ path: value.trim(), source: "guided_form" }];
  }
  return [];
}

function normalizeDelimitedRefs(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value
      .map((item) => typeof item === "string" ? item : asString(asRecord(item).path || asRecord(item).imagePath))
      .map((item) => item.trim())
      .filter(Boolean);
  }
  if (typeof value === "string") {
    return value
      .split(/[\n,]/)
      .map((item) => item.trim())
      .filter(Boolean);
  }
  return [];
}

function buildS5ProductSku(config: SceneSubmitConfig): unknown {
  const productSku = asRecord(config.product_sku);
  const existingViews = Array.isArray(productSku.views) ? productSku.views.map(asRecord) : [];
  const productViewRefs = normalizeDelimitedRefs(config.product_views);
  if (productViewRefs.length === 0) return config.product_sku || {};

  return {
    ...productSku,
    views: productViewRefs.map((ref, index) => ({
      ...(existingViews[index] || {}),
      label: asString(existingViews[index]?.label) || `view_${index + 1}`,
      imagePath: ref,
      path: ref,
    })),
  };
}

function buildProductInfo(config: SceneSubmitConfig): UnknownRecord {
  const explicitInfo = asRecord(config.product_info);
  const product = firstProduct(config);
  return definedEntries({
    ...explicitInfo,
    name: asString(explicitInfo.name)
      || asString(product.name)
      || config.product_catalog?.name
      || "Product",
    brand_name: asString(explicitInfo.brand_name)
      || asString(config.brand_guidelines?.brand_name)
      || "Momcozy",
  });
}

export function buildScenarioAutoSubmitPayload(
  config: SceneSubmitConfig,
  fallbackVideoDuration = 30,
): UnknownRecord {
  const scenario = config.content_scenario || "product_direct";
  const base = basePayload(config, fallbackVideoDuration);

  if (scenario === "brand_campaign") {
    return {
      ...base,
      target_platforms: config.target_platforms || ["tiktok"],
      target_languages: config.target_languages || ["en"],
      week: config.week || config.content_calendar_week || "",
      brand_package: buildBrandPackage(config),
    };
  }

  if (scenario === "influencer_remix") {
    return {
      ...base,
      target_platforms: config.target_platforms || ["tiktok"],
      target_languages: config.target_languages || ["en"],
      video_url: config.video_url || "",
      product: buildS3Product(config),
      influencer_name: config.influencer_name || "Influencer",
      brief_id: config.brief_id || "",
    };
  }

  if (scenario === "live_shoot" || scenario === "live_shoot_to_video") {
    return {
      ...base,
      target_platforms: config.target_platforms || ["tiktok"],
      footage_assets: normalizeFootageAssets(config.footage_assets),
      product_info: buildProductInfo(config),
      topic: config.topic || "",
      brand_guidelines: config.brand_guidelines || {},
    };
  }

  if (scenario === "brand_vlog") {
    return {
      ...base,
      brand_id: config.brand_id || "momcozy",
      product_sku: buildS5ProductSku(config),
      scene_id: config.scene_id || "living-room",
      selected_models: config.selected_models || [],
      story_description: config.story_description || "",
    };
  }

  return {
    ...base,
    target_platforms: config.target_platforms || ["tiktok"],
    target_languages: config.target_languages || ["en"],
    week: config.week || config.content_calendar_week || "",
    product_catalog: config.product_catalog,
    brand_guidelines: config.brand_guidelines,
  };
}

export function buildS1EditedStateUpdate(
  stepName: string,
  editedOutput: unknown,
): UnknownRecord {
  return {
    steps: {
      [stepName]: {
        edited: true,
        edited_output: editedOutput,
      },
    },
  };
}
