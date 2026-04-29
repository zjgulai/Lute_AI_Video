"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import CandidateSelector, { type Candidate } from "@/components/CandidateSelector";
import { useI18n } from "@/i18n/I18nProvider";
import { API_BASE } from "./api";

// Detect demo mode (same logic as api.ts)
const IS_DEMO =
  typeof process !== "undefined" &&
  ((process as any).env?.NEXT_PUBLIC_IS_DEMO === "true" ||
    (typeof window !== "undefined" &&
      (window.location.hostname.includes("github.io") ||
        window.location.hostname.endsWith(".vercel.app"))));

function getHeaders(): Record<string, string> {
  const apiKey =
    (typeof process !== "undefined" &&
      (process as any).env?.NEXT_PUBLIC_API_KEY) ||
    "ai_video_demo_2026";
  return {
    "Content-Type": "application/json",
    "X-API-Key": apiKey,
  };
}

// ── Demo candidate generators ──

async function generateDemoCandidates(gateId: string): Promise<Candidate[]> {
  const { DEMO_RESULT_1 } = await import("@/demo-data");
  const demo = DEMO_RESULT_1;

  switch (gateId) {
    case "gate_1_script": {
      const scripts = demo.scripts || [];
      if (scripts.length === 0) return [];
      const variants: Array<"standard" | "creative" | "conservative"> = ["standard", "creative", "conservative"];
      return scripts.slice(0, 3).map((s: any, i: number) => ({
        id: `script-${i + 1}`,
        variant: variants[i % variants.length],
        score: { overall: 0.85 + Math.random() * 0.12, explanation: "Strong script with clear structure" },
        data: s,
        recommended: i === 0,
      }));
    }
    case "gate_2_keyframe": {
      const boards = demo.storyboards || [];
      if (boards.length === 0) return [];
      return boards.slice(0, 3).map((b: any, i: number) => ({
        id: `keyframe-${i + 1}`,
        variant: (i === 0 ? "standard" : i === 1 ? "creative" : "conservative") as "standard" | "creative" | "conservative",
        score: { overall: 0.82 + Math.random() * 0.15, explanation: "Good visual composition" },
        data: b,
        recommended: i === 0,
      }));
    }
    case "gate_3_clips": {
      const clips = demo.seedance_output?.clip_details || [];
      if (clips.length === 0) return [];
      return clips.slice(0, 3).map((c: any, i: number) => ({
        id: `clip-${i + 1}`,
        variant: (i === 0 ? "standard" : i === 1 ? "creative" : "conservative") as "standard" | "creative" | "conservative",
        score: { overall: 0.88 + Math.random() * 0.1, explanation: "High quality clip generation" },
        data: c,
        recommended: i === 0,
      }));
    }
    case "gate_4_final": {
      return [
        {
          id: "final-1",
          variant: "standard" as const,
          score: { overall: 0.91, explanation: "Excellent final output" },
          data: {
            final_video_path: demo.final_video_path,
            audit_report: demo.audit_report,
            thumbnail_image_paths: demo.thumbnail_image_paths,
            duration: demo.seedance_output?.total_duration || demo.video_duration,
          },
          recommended: true,
        },
      ];
    }
    default:
      return [];
  }
}

interface Props {
  label: string;
  gateId: string; // "gate_1_script" | "gate_2_keyframe" | "gate_3_clips" | "gate_4_final"
  gateLabel: string;
  maxSelections: number;
  currentStep: number;
  totalSteps: number;
  onApprove: (selectedIds: string[]) => void;
  onBack: () => void;
}

export default function GatePanel({
  label,
  gateId,
  gateLabel,
  maxSelections,
  currentStep,
  totalSteps,
  onApprove,
  onBack,
}: Props) {
  const { t } = useI18n();
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingText, setLoadingText] = useState(t("gate.generating"));
  const [error, setError] = useState<string | null>(null);
  const [approving, setApproving] = useState(false);
  const [approved, setApproved] = useState(false);
  const [editCandidateId, setEditCandidateId] = useState<string | null>(null);
  const hasGenerated = useRef(false);

  const scenario = label.startsWith("s") ? label.charAt(0) + label.charAt(1) : "s1";

  // Generate candidates on mount
  const generateCandidates = useCallback(async () => {
    setLoading(true);
    setLoadingText(t("gate.generating"));
    setError(null);
    hasGenerated.current = true;

    // Demo mode: generate candidates from mock data
    if (IS_DEMO) {
      try {
        const demoCandidates = await generateDemoCandidates(gateId);
        setCandidates(demoCandidates);
      } catch (e: any) {
        console.error("GatePanel demo generate error:", e);
        setError(e.message || String(e));
      } finally {
        setLoading(false);
      }
      return;
    }

    try {
      const res = await fetch(
        `${API_BASE}/scenario/${scenario}/gate/${label}/${gateId}/generate`,
        { method: "POST", headers: getHeaders() }
      );
      if (!res.ok) {
        const errBody = await res.json().catch(() => ({}));
        throw new Error(errBody?.detail || `Generate failed (${res.status})`);
      }
      const data = await res.json();
      setCandidates(data.candidates || []);
    } catch (e: any) {
      console.error("GatePanel generate error:", e);
      setError(e.message || String(e));
    } finally {
      setLoading(false);
    }
  }, [scenario, label, gateId, t]);

  useEffect(() => {
    if (!hasGenerated.current) {
      generateCandidates();
    }
  }, [generateCandidates]);

  const handleSelectionChange = (ids: string[]) => {
    setSelectedIds(ids);
  };

  const handleEdit = (candidateId: string) => {
    setEditCandidateId(candidateId);
    // For now, we log the edit request. In a full implementation,
    // this could open an inline editor or modal.
    console.log("Edit requested for candidate:", candidateId);
  };

  const handleRegenerate = async (candidateId: string) => {
    setLoading(true);
    setLoadingText(t("gate.regenerating"));

    // Demo mode: rotate candidates
    if (IS_DEMO) {
      try {
        const fresh = await generateDemoCandidates(gateId);
        // Slightly shuffle scores to simulate regeneration
        setCandidates(
          fresh.map((c) => ({
            ...c,
            score: {
              overall: Math.min(0.99, (c.score?.overall || 0.8) + (Math.random() - 0.5) * 0.1),
              explanation: c.score?.explanation || "Regenerated variant",
            },
          }))
        );
      } catch (e: any) {
        console.error("GatePanel demo regenerate error:", e);
        setError(e.message || String(e));
      } finally {
        setLoading(false);
      }
      return;
    }

    try {
      const res = await fetch(
        `${API_BASE}/scenario/${scenario}/gate/${label}/${gateId}/regenerate/${candidateId}`,
        { method: "POST", headers: getHeaders() }
      );
      if (!res.ok) {
        const errBody = await res.json().catch(() => ({}));
        throw new Error(errBody?.detail || `Regenerate failed (${res.status})`);
      }
      // Refresh all candidates after regeneration
      const stateRes = await fetch(
        `${API_BASE}/scenario/${scenario}/gate/${label}/${gateId}`,
        { headers: getHeaders() }
      );
      if (stateRes.ok) {
        const stateData = await stateRes.json();
        setCandidates(stateData.candidates || []);
      }
    } catch (e: any) {
      console.error("GatePanel regenerate error:", e);
      setError(e.message || String(e));
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async () => {
    if (selectedIds.length === 0) return;
    setApproving(true);

    // Demo mode: skip API, directly approve
    if (IS_DEMO) {
      setApproved(true);
      setTimeout(() => {
        onApprove(selectedIds);
      }, 800);
      setApproving(false);
      return;
    }

    try {
      const res = await fetch(
        `${API_BASE}/scenario/${scenario}/gate/${label}/${gateId}/approve`,
        {
          method: "POST",
          headers: getHeaders(),
          body: JSON.stringify({ selected_ids: selectedIds }),
        }
      );
      if (!res.ok) {
        const errBody = await res.json().catch(() => ({}));
        throw new Error(errBody?.detail || `Approve failed (${res.status})`);
      }
      setApproved(true);
      // Brief success display then call onApprove
      setTimeout(() => {
        onApprove(selectedIds);
      }, 800);
    } catch (e: any) {
      console.error("GatePanel approve error:", e);
      setError(e.message || String(e));
    } finally {
      setApproving(false);
    }
  };

  // ── Progress indicator ──

  const progressLabel = `${t("app.step")} ${currentStep} / ${totalSteps}`;

  // ── Gate-specific label keys ──
  const gateLabelKey = (() => {
    switch (gateId) {
      case "gate_1_script":
        return "gate.selectScript";
      case "gate_2_keyframe":
        return "gate.reviewKeyframes";
      case "gate_3_clips":
        return "gate.selectClips";
      case "gate_4_final":
        return "gate.finalReview";
      default:
        return gateLabel;
    }
  })();

  // ── Render ──

  return (
    <div className="space-y-4 animate-slide-up">
      {/* Header card */}
      <div className="apple-card p-4">
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-3">
            <h2 className="text-base font-semibold text-[#1d1d1f]">
              {t(gateLabelKey)}
            </h2>
            <span className="text-[10px] text-[#86868b] font-mono">
              {gateId.replace(/_/g, " ")}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-[#86868b] font-medium">
              {progressLabel}
            </span>
            {/* Progress dots */}
            <div className="flex gap-1">
              {Array.from({ length: totalSteps }, (_, i) => (
                <div
                  key={i}
                  className={`w-2 h-2 rounded-full ${
                    i + 1 < currentStep
                      ? "bg-[#7CB342]"
                      : i + 1 === currentStep
                      ? "bg-[#007AFF]"
                      : "bg-[#e8e8ed]"
                  }`}
                />
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Loading state */}
      {loading && (
        <div className="apple-card p-6">
          <div className="flex flex-col items-center gap-3 py-6">
            <div className="relative w-8 h-8">
              <svg className="animate-spin w-8 h-8" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="10" stroke="#e8e8ed" strokeWidth="3" />
                <path d="M12 2a10 10 0 0 1 10 10" stroke="#7CB342" strokeWidth="3" strokeLinecap="round" />
              </svg>
            </div>
            <p className="text-sm text-[#86868b]">{loadingText}</p>
          </div>
          {/* Show skeleton during load */}
          <CandidateSelector
            candidates={[]}
            maxSelections={maxSelections}
            selectedIds={[]}
            onSelectionChange={() => {}}
            onEdit={() => {}}
          />
        </div>
      )}

      {/* Error state */}
      {error && !loading && (
        <div className="apple-card p-6 border-l-4 border-[#ff453a] bg-[#fff5f5]">
          <div className="flex items-start gap-3">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="shrink-0 mt-0.5">
              <circle cx="8" cy="8" r="7" stroke="#ff453a" strokeWidth="1.2" />
              <line x1="8" y1="4.5" x2="8" y2="8.5" stroke="#ff453a" strokeWidth="1.2" strokeLinecap="round" />
              <circle cx="8" cy="10.5" r="0.8" fill="#ff453a" />
            </svg>
            <div className="flex-1">
              <p className="text-sm font-medium text-[#ff453a] mb-1">
                {t("common.error")}
              </p>
              <p className="text-xs text-[#86868b] mb-3">{error}</p>
              <div className="flex gap-2">
                <button
                  onClick={generateCandidates}
                  className="text-xs bg-[#ff453a] text-white px-3 py-1.5 rounded-lg hover:bg-[#ff453a]/90 cursor-pointer"
                >
                  {t("step.retry")}
                </button>
                <button
                  onClick={onBack}
                  className="text-xs text-[#86868b] px-3 py-1.5 rounded-lg hover:bg-[#e8e8ed]/50 cursor-pointer"
                >
                  {t("common.cancel")}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Candidates */}
      {!loading && !error && (
        <div className="apple-card p-4">
          <CandidateSelector
            candidates={candidates}
            maxSelections={maxSelections}
            selectedIds={selectedIds}
            onSelectionChange={handleSelectionChange}
            onEdit={handleEdit}
          />

          {/* Per-candidate regeneration */}
          {candidates.length > 0 && (
            <div className="flex flex-wrap gap-2 mt-3 justify-center">
              {candidates.map((c) => (
                <button
                  key={`regen-${c.id}`}
                  onClick={() => handleRegenerate(c.id)}
                  disabled={loading}
                  className="text-[10px] text-[#86868b] hover:text-[#007AFF] transition-colors px-2 py-1 rounded hover:bg-[#e8e8ed]/30 disabled:opacity-50 cursor-pointer"
                >
                  {t("gate.regenerate")} {t(getVariantLabelKey(c.variant))}
                </button>
              ))}
            </div>
          )}

          {/* Edit panel placeholder */}
          {editCandidateId && (
            <div className="mt-3 p-3 rounded-lg bg-[#fafafc] border border-[#e8e8ed]">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[10px] font-semibold text-[#1d1d1f]">
                  {t("step.editTitle")} {editCandidateId}
                </span>
                <button
                  onClick={() => setEditCandidateId(null)}
                  className="text-[10px] text-[#86868b] hover:text-[#1d1d1f] cursor-pointer"
                >
                  {t("workflow.cancelEdit")}
                </button>
              </div>
              <pre className="text-[10px] font-mono text-[#86868b] bg-white p-2 rounded border border-[#e8e8ed] overflow-auto max-h-[200px] whitespace-pre-wrap break-all">
                {JSON.stringify(
                  candidates.find((c) => c.id === editCandidateId)?.data ?? {},
                  null,
                  2
                )}
              </pre>
            </div>
          )}

          {/* Selection hint */}
          <div className="mt-3 text-center">
            <p className="text-[10px] text-[#aeaeb2]">
              {selectedIds.length === 0
                ? t("gate.selectHint")
                : `${selectedIds.length}/${maxSelections} ${t("review.selected")}`}
            </p>
          </div>
        </div>
      )}

      {/* Approved success state */}
      {approved && (
        <div className="apple-card p-4 border-[#7CB342] bg-[#f0faf0]">
          <div className="flex items-center gap-2 justify-center">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <circle cx="8" cy="8" r="7" fill="#7CB342" />
              <path d="M5 8.5L7 10.5L11 5.5" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span className="text-sm font-medium text-[#7CB342]">
              {t("gate.approved") || "Approved, continuing..."}
            </span>
          </div>
        </div>
      )}

      {/* Action buttons */}
      {!loading && !error && !approved && (
        <div className="flex items-center justify-between">
          <button
            onClick={onBack}
            disabled={approving}
            className="text-xs text-[#86868b] px-4 py-2 rounded-lg hover:bg-[#e8e8ed]/50 transition-colors disabled:opacity-50 cursor-pointer"
          >
            {t("recommend.backToEdit")}
          </button>
          <button
            onClick={handleApprove}
            disabled={selectedIds.length === 0 || approving}
            className={`apple-btn text-xs px-5 py-2 disabled:opacity-50 ${
              selectedIds.length > 0
                ? "apple-btn-primary"
                : "bg-[#f5f5f7] text-[#aeaeb2]"
            }`}
          >
            {approving
              ? t("step.running")
              : `${t("gate.approveAndContinue")} (${selectedIds.length})`}
          </button>
        </div>
      )}
    </div>
  );
}

function getVariantLabelKey(variant: string): string {
  switch (variant) {
    case "standard":
      return "gate.variant.standard";
    case "creative":
      return "gate.variant.creative";
    case "conservative":
      return "gate.variant.conservative";
    default:
      return variant;
  }
}
