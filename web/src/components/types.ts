export interface ReviewState {
  thread_id: string;
  status: string;
  current_review: string | null;
  pipeline_complete: boolean;
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

// Must match backend REVIEW_NODES in src/models/__init__.py
export const REVIEW_NODES = [
  "strategy_review",
  "script_review",
  "edit_review",
  "thumbnail_review",
];

export const AUDIT_CHECKPOINT: Record<string, string> = {
  strategy_review: "strategy",
  script_review: "script",
  edit_review: "edit",
  thumbnail_review: "thumbnail",
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
    title: "品牌VLOG",
    desc: "基于品牌素材（六视图+模特+场景+故事）一键生成 VLOG 风格短片",
    iconName: SCENE_ICON_NAMES.brand_vlog,
    platforms: ["tiktok", "shopify", "youtube_shorts"],
  },
] as const;

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
