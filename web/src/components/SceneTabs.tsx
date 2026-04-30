"use client";

import { Users, Megaphone, Package, Zap } from "lucide-react";
import { useI18n } from "@/i18n/I18nProvider";

interface Props {
  activeScene: string;
  onChange: (sceneId: string) => void;
  videoCounts: Record<string, number>;
}

const SCENE_IDS = ["product_direct", "brand_campaign", "influencer_remix", "fast_mode"];

const SCENE_DESC_KEYS: Record<string, string> = {
  product_direct: "scene.desc.product_direct",
  brand_campaign: "scene.desc.brand_campaign",
  influencer_remix: "scene.desc.influencer_remix",
  fast_mode: "scene.desc.fast_mode",
};

const SCENE_ICON_MAP: Record<string, React.ComponentType<{ size?: number; strokeWidth?: number; className?: string }>> = {
  product_direct: Package,
  brand_campaign: Megaphone,
  influencer_remix: Users,
  fast_mode: Zap,
};

export default function SceneTabs({ activeScene, onChange, videoCounts }: Props) {
  const { t } = useI18n();

  return (
    <div className="space-y-3">
      <div className="flex items-stretch gap-1.5">
        {SCENE_IDS.map((id) => {
          const isActive = activeScene === id;
          const count = videoCounts[id] ?? 0;
          const IconComponent = SCENE_ICON_MAP[id];
          return (
            <button
              key={id}
              onClick={() => onChange(id)}
              className={`flex-1 flex items-center gap-2 px-3 py-2.5 rounded-lg border transition-all cursor-pointer ${
                isActive
                  ? "border-[#7CB342] bg-[#7CB342]/5 ring-1 ring-[#7CB342]/20"
                  : "border-[#e8e8ed] bg-white hover:border-[#d2d2d7]"
              }`}
            >
              {IconComponent && (
                <IconComponent
                  size={24}
                  strokeWidth={1.5}
                  className={`shrink-0 ${isActive ? "text-[#7CB342]" : "text-[#86868b]"}`}
                />
              )}
              <div className="text-left min-w-0">
                <span
                  className={`block text-[11px] font-semibold leading-tight ${
                    isActive ? "text-[#1d1d1f]" : "text-[#86868b]"
                  }`}
                >
                  {t(`scene.${id}.title`)}
                </span>
                {count > 0 && (
                  <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-[#7CB342]/10 text-[#7CB342]">
                    {count}{t("asset.count")}
                  </span>
                )}
              </div>
            </button>
          );
        })}
      </div>
      <p className="text-[11px] text-[#86868b] leading-relaxed px-0.5">
        {t(SCENE_DESC_KEYS[activeScene] || SCENE_DESC_KEYS.product_direct)}
      </p>
    </div>
  );
}
