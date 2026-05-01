"use client";

import { Users, Megaphone, Package, Lightning, Camera } from "@phosphor-icons/react";
import type { IconProps } from "@phosphor-icons/react";
import { useI18n } from "@/i18n/I18nProvider";
import { logUI } from "./api";

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

const SCENE_ICON_MAP: Record<string, React.ComponentType<IconProps>> = {
  product_direct: Package,
  brand_campaign: Megaphone,
  influencer_remix: Users,
  brand_vlog: Camera,
  fast_mode: Lightning,
};

export default function SceneTabs({ activeScene, onChange, videoCounts }: Props) {
  const { t } = useI18n();

  return (
    <div className="space-y-3">
      <div className="flex items-stretch gap-3">
        {SCENE_IDS.map((id) => {
          const isActive = activeScene === id;
          const count = videoCounts[id] ?? 0;
          const IconComponent = SCENE_ICON_MAP[id];
          return (
            <button
              key={id}
              onClick={() => {
                logUI("SELECT", "SceneTabs", { scene: id, from: activeScene });
                onChange(id);
              }}
              className={`flex-1 flex items-center gap-2.5 px-4 py-3.5 rounded-lg border transition-all cursor-pointer min-h-[56px] ${
                isActive
                  ? "border-[var(--fortune-red)] bg-[rgba(215,92,112,0.08)] ring-1 ring-[rgba(215,92,112,0.25)] shadow-[0_0_12px_rgba(255,77,106,0.18)]"
                  : "border-[var(--border-default)] bg-[var(--bg-card)] hover:border-[var(--fortune-red)] hover:bg-[rgba(215,92,112,0.04)]"
              }`}
            >
              {IconComponent && (
                <IconComponent
                  size={20}
                  weight="fill"
                  className={`shrink-0 ${isActive ? "text-[var(--fortune-red)]" : "text-[var(--text-muted)]"}`}
                />
              )}
              <div className="text-left min-w-0">
                <span
                  className={`block text-[13px] font-semibold leading-tight ${
                    isActive ? "text-[var(--text-h1)]" : "text-[var(--text-body)]"
                  }`}
                >
                  {t(`scene.${id}.title`)}
                </span>
                {count > 0 && (
                  <span className="text-[11px] font-medium px-1.5 py-0.5 rounded-full bg-[rgba(215,92,112,0.12)] text-[var(--fortune-red)]">
                    {count}{t("asset.count")}
                  </span>
                )}
              </div>
            </button>
          );
        })}
      </div>
      <p className="text-[11px] text-[var(--text-muted)] leading-relaxed px-0.5">
        {t(SCENE_DESC_KEYS[activeScene] || SCENE_DESC_KEYS.product_direct)}
      </p>
    </div>
  );
}
