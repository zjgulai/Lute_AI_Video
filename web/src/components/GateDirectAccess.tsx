"use client";

import { useRouter } from "next/navigation";
import { useI18n } from "@/i18n/I18nProvider";
import GatePanel from "@/components/GatePanel";
import { apiFetch } from "@/components/api";

const GATE_INDEX_TO_DEF = (t: (key: string, fallback?: string) => string) => [
  { gateId: "gate_1_script", gateLabel: t("gate.selectScript"), maxSelections: 2 },
  { gateId: "gate_2_keyframe", gateLabel: t("gate.reviewKeyframes"), maxSelections: 1 },
  { gateId: "gate_3_clips", gateLabel: t("gate.selectClips"), maxSelections: 1 },
  { gateId: "gate_4_final", gateLabel: t("gate.finalReview"), maxSelections: 1 },
];

interface Props {
  scene: "s1" | "s2" | "s3" | "s4" | "s5";
  label: string;
  gateNumber: 1 | 2 | 3 | 4;
}

export default function GateDirectAccess({ scene, label, gateNumber }: Props) {
  const { t } = useI18n();
  const router = useRouter();
  const sequence = GATE_INDEX_TO_DEF(t);
  const def = sequence[gateNumber - 1];

  if (!def) {
    return (
      <div className="apple-card p-8 max-w-2xl mx-auto mt-12 text-center">
        <p className="text-lg font-semibold mb-2">{t("gate.invalidNumber", "Invalid gate number")}</p>
        <p className="text-sm text-[var(--color-text-tertiary)]">
          {t("gate.invalidNumberHint", "Gate must be 1, 2, 3, or 4")} ({gateNumber})
        </p>
      </div>
    );
  }

  const handleApprove = async (selectedIds: string[]) => {
    try {
      await apiFetch(`/scenario/${scene}/gate/${label}/${def.gateId}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ selected_candidate_ids: selectedIds }),
      });
      router.push(`/${scene}?label=${encodeURIComponent(label)}`);
    } catch (e) {
      console.error("[GateDirectAccess] approve failed", e);
    }
  };

  const handleBack = () => {
    router.push(`/${scene}`);
  };

  return (
    <div className="max-w-6xl mx-auto p-4">
      <div className="mb-4 text-sm text-[var(--color-text-tertiary)]">
        <span>{t("gate.directAccessLabel", "Direct gate review")}: </span>
        <code className="text-xs bg-[var(--bg-card)] px-2 py-0.5 rounded">{label}</code>
        <span className="mx-2">·</span>
        <span>{def.gateLabel}</span>
      </div>
      <GatePanel
        label={label}
        gateId={def.gateId}
        gateLabel={def.gateLabel}
        maxSelections={def.maxSelections}
        currentStep={gateNumber}
        totalSteps={sequence.length}
        gateSequence={sequence}
        onApprove={handleApprove}
        onBack={handleBack}
      />
    </div>
  );
}
