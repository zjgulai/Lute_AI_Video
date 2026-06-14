"use client";

import React from "react";
import { Package } from "@phosphor-icons/react";
import { useI18n } from "@/i18n/I18nProvider";

interface Props {
  onSubmit: (config: Record<string, unknown>) => void;
  productName: string;
  setProductName: (v: string) => void;
  keyFeatures: string;
  setKeyFeatures: (v: string) => void;
  usageScenario: string;
  setUsageScenario: (v: string) => void;
  painPoints: string;
  setPainPoints: (v: string) => void;
  productTargetAudience: string;
  setProductTargetAudience: (v: string) => void;
  competitorContext: string;
  setCompetitorContext: (v: string) => void;
  continuityMode: string;
  setContinuityMode: (v: string) => void;
  mode: string;
}

export default function ProductDirectForm({ productName, setProductName }: Props) {
  const { t } = useI18n();
  return (
    <div className="space-y-3">
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
        {/* S1-specific fields continue from the legacy SceneForm —
             for a full migration, extract all S1 fields here */}
      </div>
    </div>
  );
}
