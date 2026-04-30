"use client";

import { useI18n } from "@/i18n/I18nProvider";

const TIERS = [
  { seconds: 15, label: "5-15s", sceneKey: "duration.ultraShort" },
  { seconds: 30, label: "15-30s", sceneKey: "duration.standard" },
  { seconds: 45, label: "30-45s", sceneKey: "duration.extended" },
  { seconds: 60, label: "45-60s", sceneKey: "duration.mediumLong" },
  { seconds: 90, label: "60-90s", sceneKey: "duration.long" },
] as const;

interface Props {
  value: number;
  onChange: (seconds: number) => void;
}

export default function DurationSlider({ value, onChange }: Props) {
  const { t } = useI18n();

  return (
    <div className="apple-card p-3">
      <h3 className="text-[11px] font-semibold text-[#9FA0A0] uppercase tracking-wider mb-2">
        {t("duration.label")}
      </h3>
      <p className="text-[9px] text-[#9FA0A0] mb-2 leading-tight">
        {t("duration.hint")}
      </p>
      <div className="flex gap-1.5">
        {TIERS.map((tier) => {
          const active = value === tier.seconds;
          return (
            <button
              key={tier.seconds}
              onClick={() => onChange(tier.seconds)}
              className={`
                flex-1 flex flex-col items-center py-2 rounded-xl text-center
                transition-all duration-200 cursor-pointer select-none
                ${
                  active
                    ? "bg-gradient-to-br from-[#5B8DEF] to-[#7C3AED] text-white shadow-md scale-[1.02]"
                    : "bg-[#FFF0EF] text-[#35353B] hover:bg-[#EDD3D1] active:scale-95"
                }
              `}
            >
              <span className="text-sm font-bold tabular-nums leading-tight">
                {tier.label}
              </span>
              <span
                className={`text-[10px] leading-tight mt-0.5 ${
                  active ? "text-white/80" : "text-[#9FA0A0]"
                }`}
              >
                {t(tier.sceneKey)}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
