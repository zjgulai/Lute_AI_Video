export interface ReviewState {
  thread_id: string;
  status: string;
  current_review: string | null;
  pipeline_complete: boolean;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  state: any;
}

export interface AuditCriterion {
  name: string;
  score: number;
  status: "PASS" | "WARN" | "FAIL";
  reason?: string;
}

export interface AuditReport {
  overall_score: number;
  overall_status: "PASS" | "WARN" | "FAIL";
  summary: string;
  criteria: AuditCriterion[];
}

// Gate system nodes (StepRunner era). Legacy LangGraph nodes deprecated.
export const REVIEW_NODES = [
  "gate_1_script",
  "gate_2_keyframe",
  "gate_3_clips",
  "gate_4_final",
];

export const AUDIT_CHECKPOINT: Record<string, string> = {
  gate_1_script: "script",
  gate_2_keyframe: "keyframe",
  gate_3_clips: "clips",
  gate_4_final: "final",
};

export const SEGMENT_LABELS: Record<string, string> = {
  hook: "Hook",
  pain_point: "Pain Point",
  solution: "Solution",
  trust_building: "Trust Building",
  cta: "CTA",
  body: "Body",
  pitch: "Pitch",
  intro: "Intro",
  conclusion: "Conclusion",
  scene_drop: "Scene Drop",
  comparison: "Comparison",
  data_drop: "Data Drop",
  question: "Question",
  story_hook: "Story Hook",
  counter_narrative: "Counter Narrative",
  reaction: "Reaction",
  emotional: "Emotional",
  testimonial: "Testimonial",
  tutorial: "Tutorial",
};

export const PLATFORM_LABELS: Record<string, string> = {
  shopify: "Shopify",
  amazon: "Amazon",
  tiktok: "TikTok",
  reddit: "Reddit",
  facebook: "Facebook",
  youtube_shorts: "YouTube Shorts",
};

export const SCENE_ICON_NAMES: Record<string, string> = {
  influencer_remix: "Users",
  brand_campaign: "Megaphone",
  product_direct: "Package",
  brand_vlog: "Camera",
  general: "Zap",
  live_shoot_to_video: "Camera",
};

export const PLATFORM_ICON_NAMES: Record<string, string> = {
  shopify: "ShoppingBag",
  amazon: "ShoppingCart",
  tiktok: "Music",
  reddit: "MessageCircle",
  facebook: "ExternalLink",
  youtube_shorts: "Video",
};

export const STAGE_ICON_NAMES: Record<string, string> = {
  strategy: "Clock",
  script: "FileText",
  compliance: "CheckCircle",
  storyboard: "Image",
  asset_sourcing: "Search",
  media_gen: "Video",
  editing: "PenSquare",
  audio: "Headphones",
  caption: "Type",
  thumbnail: "Image",
  analytics: "BarChart3",
  distribution: "Repeat",
};

export const CONTENT_SCENARIOS = [
  {
    id: "influencer_remix",
    title: "Influencer Remix",
    desc: "Employee IP with contracted influencers distributing content with product links",
    iconName: SCENE_ICON_NAMES.influencer_remix,
    platforms: ["shopify", "amazon", "tiktok", "reddit"],
  },
  {
    id: "brand_campaign",
    title: "Brand Campaign",
    desc: "Professional brand showcase with unified multi-platform messaging",
    iconName: SCENE_ICON_NAMES.brand_campaign,
    platforms: ["shopify", "tiktok", "youtube_shorts"],
  },
  {
    id: "product_direct",
    title: "Product Direct",
    desc: "Input product info directly, AI generates product showcase videos and thumbnails",
    iconName: SCENE_ICON_NAMES.product_direct,
    platforms: ["tiktok", "shopify"],
  },
  {
    id: "brand_vlog",
    title: "Brand VLOG",
    desc: "Select product SKU to auto-fill six-view, choose model roles, input story direction, AI generates a complete VLOG narrative video.",
    iconName: SCENE_ICON_NAMES.brand_vlog,
    platforms: ["tiktok", "shopify", "youtube_shorts"],
  },
] as const;

// ═══ 会说话的 UI 2.0 — 引导卡片系统类型 ═══

export type CardPriority = "required" | "recommended" | "optional";

export interface VideoType {
  id: string;
  name: string;
  desc: string;
}

export interface GuidedCard {
  priority: CardPriority;
  stepName: string;
  stepIcon: string;
  question: string;
  reason: string;
  connectionText: string;
  fieldKey: string;
  inputType: "text" | "textarea" | "select" | "multiselect" | "image-upload" | "video-upload" | "toggle" | "duration";
  options?: string[];
  placeholder?: string;
  maxLength?: number;
}

export interface CardSequence {
  scene: string;
  videoType: string;
  cards: GuidedCard[];
}

export interface LiveSummaryEntry {
  label: string;
  value: string;
  icon: string;
}

export interface TemplatePreset {
  id: string;
  name: string;
  nameEn: string;
  scene: string;
  videoType: string;
  values: Record<string, string>;
  description?: string;
  descriptionEn?: string;
}

// 品牌VLOG — 产品六视图角度
export interface ProductViewAngle {
  label: string;
  title: string;
  description: string;
  usage_note: string;
  color: string;
}

// 品牌VLOG — 产品SKU
export interface ProductSku {
  id: string;
  name: string;
  shortName: string;
  description: string;
  tags: string[];
  views: ProductViewAngle[];
}

// 品牌VLOG — 模特
export interface ModelProfile {
  id: string;
  name: string;
  role: string;
  description: string;
  gradient: [string, string];
}

// 品牌VLOG — 品牌定义
export interface VlogBrand {
  id: string;
  name: string;
  tone: string;
}
