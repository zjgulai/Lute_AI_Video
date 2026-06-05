import type { Icon } from "@phosphor-icons/react";
import {
  FilmSlate,
  ImageSquare,
  MagicWand,
  SquaresFour,
  UserFocus,
} from "@phosphor-icons/react";
import type { ToolboxToolId } from "@/components/api";

export type ToolPresentation = {
  id: ToolboxToolId;
  titleKey: string;
  descriptionKey: string;
  icon: Icon;
  accentClassName: string;
  fallbackOutputTypes: string[];
  fallbackScenarios: string[];
  fallbackChecks: string[];
};

export const TOOL_ORDER: ToolboxToolId[] = [
  "product-image",
  "six-view",
  "ecommerce-visual",
  "digital-human",
  "storyboard",
];

export const TOOL_PRESENTATION: Record<ToolboxToolId, ToolPresentation> = {
  "product-image": {
    id: "product-image",
    titleKey: "toolbox.productImage",
    descriptionKey: "toolbox.productImage.desc",
    icon: ImageSquare,
    accentClassName: "bg-[rgba(215,92,112,0.10)] text-[var(--fortune-red)]",
    fallbackOutputTypes: ["product_image_set", "artifact_manifest"],
    fallbackScenarios: ["S1", "S2", "S5"],
    fallbackChecks: ["product_facts", "claim_evidence", "brand_bounds"],
  },
  "six-view": {
    id: "six-view",
    titleKey: "toolbox.sixView",
    descriptionKey: "toolbox.sixView.desc",
    icon: SquaresFour,
    accentClassName: "bg-[rgba(28,125,115,0.12)] text-[#1c7d73]",
    fallbackOutputTypes: ["six_view_manifest", "reference_set"],
    fallbackScenarios: ["S1", "S2", "S5"],
    fallbackChecks: ["view_coverage", "identity_consistency", "asset_rights"],
  },
  "ecommerce-visual": {
    id: "ecommerce-visual",
    titleKey: "toolbox.ecommerceVisual",
    descriptionKey: "toolbox.ecommerceVisual.desc",
    icon: MagicWand,
    accentClassName: "bg-[rgba(183,129,44,0.14)] text-[#a66b1f]",
    fallbackOutputTypes: ["visual_pack", "layout_manifest"],
    fallbackScenarios: ["S1", "S2"],
    fallbackChecks: ["platform_layout", "brand_bounds", "safe_zone"],
  },
  "digital-human": {
    id: "digital-human",
    titleKey: "toolbox.digitalHuman",
    descriptionKey: "toolbox.digitalHuman.desc",
    icon: UserFocus,
    accentClassName: "bg-[rgba(78,102,189,0.12)] text-[#4e66bd]",
    fallbackOutputTypes: ["presenter_plan", "avatar_job_draft"],
    fallbackScenarios: ["S2", "S4", "S5"],
    fallbackChecks: ["likeness_consent", "voice_consent", "no_live_default"],
  },
  storyboard: {
    id: "storyboard",
    titleKey: "toolbox.storyboard",
    descriptionKey: "toolbox.storyboard.desc",
    icon: FilmSlate,
    accentClassName: "bg-[rgba(97,82,67,0.12)] text-[#715947]",
    fallbackOutputTypes: ["shot_ledger", "timeline_manifest", "edl_seed"],
    fallbackScenarios: ["S1", "S2", "S3", "S4", "S5"],
    fallbackChecks: ["timeline_blocks", "shot_continuity", "review_checkpoint"],
  },
};

export function isToolboxToolId(value: string): value is ToolboxToolId {
  return TOOL_ORDER.includes(value as ToolboxToolId);
}

export function getToolPresentation(toolId: ToolboxToolId): ToolPresentation {
  return TOOL_PRESENTATION[toolId];
}

export function formatToolboxList(values: string[]): string {
  return values.length > 0 ? values.join(" / ") : "-";
}
