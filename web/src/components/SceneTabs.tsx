"use client";

import { Users, Megaphone, Package, Zap, Camera } from "lucide-react";
import { useI18n } from "@/i18n/I18nProvider";

interface Props {
  activeScene: string;
  onChange: (sceneId: string) => void;
  videoCounts: Record<string, number>;
}

const SCENE_IDS = ["product_direct", "brand_campaign", "influencer_remix", "brand_vlog", "fast_mode"];

const SCENE_DESC_KEYS: Record<string, string> = {
  product_direct: "scene.desc.product_direct",
  brand_campaign: "scene.desc.brand_campaign",
  influencer_remix: "scene.desc.influencer_remix",
  brand_vlog: "scene.desc.brand_vlog",
  fast_mode: "scene.desc.fast_mode",
};

const SCENE_ICON_MAP: Record<string, React.ComponentType<{ size?: number; strokeWidth?: number; className?: string }>> = {
  product_direct: Package,
  brand_campaign: Megaphone,
  influencer_remix: Users,
  brand_vlog: Camera,
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
                  ? "border-[#6A2B3A] bg-[#6A2B3A]/5 ring-1 ring-[#6A2B3A]/20"
                  : "border-[#EDD3D1] bg-white hover:border-[#D9A8A3]"
              }`}
            >
              {IconComponent && (
                <IconComponent
                  size={24}
                  strokeWidth={1.5}
                  className={`shrink-0 ${isActive ? "text-[#6A2B3A]" : "text-[#59585E]"}`}
                />
              )}
              <div className="text-left min-w-0">
                <span
                  className={`block text-[11px] font-semibold leading-tight ${
                    isActive ? "text-[#35353B]" : "text-[#59585E]"
                  }`}
                >
                  {t(`scene.${id}.title`)}
                </span>
                {count > 0 && (
                  <span className="text-[11px] font-medium px-1.5 py-0.5 rounded-full bg-[#6A2B3A]/10 text-[#6A2B3A]">
                    {count}{t("asset.count")}
                  </span>
                )}
              </div>
            </button>
          );
        })}
      </div>
      <p className="text-[11px] text-[#59585E] leading-relaxed px-0.5">
        {t(SCENE_DESC_KEYS[activeScene] || SCENE_DESC_KEYS.product_direct)}
      </p>
    </div>
  );
}
