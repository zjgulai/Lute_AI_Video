"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import CandidateSelector, {
  normalizeCandidateData,
  normalizeCandidates,
  type Candidate,
  type CandidateVariant,
} from "@/components/CandidateSelector";
import InlineTooltip from "@/components/InlineTooltip";
import { useI18n } from "@/i18n/I18nProvider";
import { isDemoMode, getScenarioStatus, apiFetch, fetchGateState } from "./api";
import {
  getContinuityDiagnosticsSummary,
  hasContinuityDiagnostics,
  normalizeContinuityDiagnostics,
  type ContinuityDiagnosticsPayload,
} from "@/lib/continuityDiagnostics";
import { truncateDiagnosticText } from "@/lib/diagnosticText";
import { errorMessage } from "@/lib/errors";
// P1-A: 删除本地 getHeaders + 硬编码 demo key,
// 全部走 apiFetch() 自动注入 X-API-Key + 自动拼 base URL,
// SettingsPanel 修改 API key 后立即对所有 Gate 操作生效。

// ── Demo candidate generators ──

async function generateDemoCandidates(gateId: string): Promise<Candidate[]> {
  const { DEMO_RESULT_1 } = await import("@/demo-data");
  const demo = DEMO_RESULT_1;

  switch (gateId) {
    case "gate_1_script": {
      const scripts = demo.scripts || [];
      if (scripts.length === 0) return [];
      const variants: CandidateVariant[] = ["standard", "creative", "conservative"];
      return scripts.slice(0, 3).map((s, i) => ({
        id: `script-${i + 1}`,
        variant: variants[i % variants.length],
        score: { overall: 0.85 + Math.random() * 0.12, explanation: "Strong script with clear structure" },
        data: normalizeCandidateData(s),
        recommended: i === 0,
      }));
    }
    case "gate_2_keyframe": {
      const boards = demo.storyboards || [];
      if (boards.length === 0) return [];
      return boards.slice(0, 3).map((b, i) => ({
        id: `keyframe-${i + 1}`,
        variant: (i === 0 ? "standard" : i === 1 ? "creative" : "conservative") as CandidateVariant,
        score: { overall: 0.82 + Math.random() * 0.15, explanation: "Good visual composition" },
        data: normalizeCandidateData(b),
        recommended: i === 0,
      }));
    }
    case "gate_3_clips": {
      const clips = demo.seedance_output?.clip_details || [];
      if (clips.length === 0) return [];
      return clips.slice(0, 3).map((c, i) => ({
        id: `clip-${i + 1}`,
        variant: (i === 0 ? "standard" : i === 1 ? "creative" : "conservative") as CandidateVariant,
        score: { overall: 0.88 + Math.random() * 0.1, explanation: "High quality clip generation" },
        data: normalizeCandidateData(c),
        recommended: i === 0,
      }));
    }
    case "gate_4_final": {
      return [
        {
          id: "final-1",
          variant: "standard" as const,
          score: { overall: 0.91, explanation: "Excellent final output" },
          data: normalizeCandidateData({
            final_video_path: demo.final_video_path,
            audit_report: demo.audit_report,
            thumbnail_image_paths: demo.thumbnail_image_paths,
            duration: demo.seedance_output?.total_duration || demo.video_duration,
          }),
          recommended: true,
        },
      ];
    }
    default:
      return [];
  }
}

interface GateDef {
  gateId: string;
  gateLabel: string;
  maxSelections: number;
}

interface Props {
  label: string;
  gateId: string; // "gate_1_script" | "gate_2_keyframe" | "gate_3_clips" | "gate_4_final"
  gateLabel: string;
  maxSelections: number;
  currentStep: number;
  totalSteps: number;
  gateSequence?: GateDef[];
  onApprove: (selectedIds: string[]) => void;
  onBack: () => void;
}

type GatePollFailure = "stalled" | "timeout" | "exception";

interface GateResumePollingContext {
  selectedIds: string[];
  nextGateId: string | null;
  isLastGate: boolean;
}

const GATE_RESUME_MAX_POLLS = 360;
const GATE_RESUME_INITIAL_DELAY_MS = 3000;
const GATE_RESUME_INTERVAL_MS = 5000;
const GATE_RESUME_FAILURE_STATUSES = new Set([
  "error",
  "failed",
  "invalid_state",
  "policy_blocked",
  "recovery_required",
]);
const GATE_TERMINAL_STATUSES = new Set(["completed_bounded", "completed_full"]);

function isCoherentGateTerminal(state: {
  status?: unknown;
  lifecycle_status?: unknown;
  completion_kind?: unknown;
  request_succeeded?: unknown;
  success?: unknown;
  full_media_success?: unknown;
  pipeline_complete?: unknown;
  publish_allowed?: unknown;
  delivery_accepted?: unknown;
}): boolean {
  if (state.status === "completed_bounded") {
    return state.lifecycle_status === "completed_bounded"
      && (state.completion_kind === "no_media" || state.completion_kind === "bounded_media")
      && state.request_succeeded === true
      && state.success === false
      && state.full_media_success === false
      && state.pipeline_complete === false
      && state.publish_allowed === false
      && state.delivery_accepted === false;
  }
  if (state.status === "completed_full") {
    return state.lifecycle_status === "completed_full"
      && state.completion_kind === "full_media"
      && state.request_succeeded === true
      && state.success === true
      && state.full_media_success === true
      && state.pipeline_complete === true
      && state.publish_allowed === false
      && state.delivery_accepted === false;
  }
  return false;
}

function getRuntimeStatus(value: unknown): string {
  if (!value || typeof value !== "object" || Array.isArray(value)) return "";
  const status = (value as { status?: unknown }).status;
  return typeof status === "string" ? status : "";
}

function summarizeRuntimeStatuses(value: unknown): string[] {
  if (!value || typeof value !== "object" || Array.isArray(value)) return [];
  return Object.entries(value).map(([key, item]) => `${key}:${getRuntimeStatus(item)}`);
}

export default function GatePanel({
  label,
  gateId,
  gateLabel,
  maxSelections,
  currentStep,
  totalSteps,
  gateSequence,
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
  const [processing, setProcessing] = useState(false);
  const [pollFailure, setPollFailure] = useState<GatePollFailure | null>(null);
  const [editCandidateId, setEditCandidateId] = useState<string | null>(null);
  const [continuityDiagnostics, setContinuityDiagnostics] = useState<ContinuityDiagnosticsPayload | null>(null);
  const hasGenerated = useRef(false);
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const resumePollingContextRef = useRef<GateResumePollingContext | null>(null);
  const resumeCompletedRef = useRef(false);
  const mountedRef = useRef(true);

  const scenario = label.startsWith("s") ? label.charAt(0) + label.charAt(1) : "s1";

  const loadGateState = useCallback(async () => {
    const stateData = await fetchGateState(scenario, label, gateId);
    setCandidates(normalizeCandidates(stateData.candidates));
    setContinuityDiagnostics(stateData.continuity_diagnostics || null);
  }, [scenario, label, gateId]);

  // Generate candidates on mount
  const generateCandidates = useCallback(async () => {
    setLoading(true);
    setLoadingText(t("gate.generating"));
    setError(null);
    hasGenerated.current = true;

    // Demo mode: generate candidates from mock data
    if (isDemoMode()) {
      try {
        const demoCandidates = await generateDemoCandidates(gateId);
        setCandidates(demoCandidates);
        setContinuityDiagnostics(null);
      } catch (e: unknown) {
        console.error("GatePanel demo generate error:", e);
        setError(errorMessage(e));
      } finally {
        setLoading(false);
      }
      return;
    }

    try {
      const res = await apiFetch(
        `/scenario/${scenario}/gate/${label}/${gateId}/generate`,
        { method: "POST" }
      );
      if (!res.ok) {
        const errBody = await res.json().catch(() => ({}));
        throw new Error(errBody?.detail || `Generate failed (${res.status})`);
      }
      await loadGateState();
    } catch (e: unknown) {
      console.error("GatePanel generate error:", e);
      setError(errorMessage(e));
    } finally {
      setLoading(false);
    }
  }, [gateId, loadGateState, scenario, label, t]);

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
    if (isDemoMode()) {
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
        setContinuityDiagnostics(null);
      } catch (e: unknown) {
        console.error("GatePanel demo regenerate error:", e);
        setError(errorMessage(e));
      } finally {
        setLoading(false);
      }
      return;
    }

    try {
      const res = await apiFetch(
        `/scenario/${scenario}/gate/${label}/${gateId}/regenerate/${candidateId}`,
        { method: "POST" }
      );
      if (!res.ok) {
        const errBody = await res.json().catch(() => ({}));
        throw new Error(errBody?.detail || `Regenerate failed (${res.status})`);
      }
      await loadGateState();
    } catch (e: unknown) {
      console.error("GatePanel regenerate error:", e);
      setError(errorMessage(e));
    } finally {
      setLoading(false);
    }
  };

  const clearPollTimer = useCallback(() => {
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  const completeResumePolling = useCallback((ids: string[]) => {
    if (!mountedRef.current || resumeCompletedRef.current) return;
    resumeCompletedRef.current = true;
    clearPollTimer();
    setProcessing(false);
    setPollFailure(null);
    onApprove(ids);
  }, [clearPollTimer, onApprove]);

  const startResumePolling = useCallback((context: GateResumePollingContext) => {
    clearPollTimer();
    resumePollingContextRef.current = context;
    resumeCompletedRef.current = false;
    setPollFailure(null);
    setProcessing(true);

    let lastStateHash = "";
    let stableCount = 0;

    const failClosed = (reason: GatePollFailure) => {
      if (!mountedRef.current) return;
      clearPollTimer();
      setProcessing(false);
      setPollFailure(reason);
    };

    const poll = async (pollCount: number) => {
      if (!mountedRef.current || resumeCompletedRef.current) return;
      if (pollCount >= GATE_RESUME_MAX_POLLS) {
        failClosed("timeout");
        return;
      }

      try {
        const state = await getScenarioStatus(scenario, label);
        if (!mountedRef.current || resumeCompletedRef.current) return;
        const gates = state.gates || {};
        const currentStepName = state.current_step;

        const lifecycleStatus = typeof state.lifecycle_status === "string"
          ? state.lifecycle_status
          : "";
        if (
          state.pipeline_degraded
          || GATE_RESUME_FAILURE_STATUSES.has(state.status)
          || GATE_RESUME_FAILURE_STATUSES.has(lifecycleStatus)
        ) {
          failClosed("exception");
          return;
        }
        const coherentTerminal = isCoherentGateTerminal(state);
        const claimsTerminal = GATE_TERMINAL_STATUSES.has(state.status)
          || GATE_TERMINAL_STATUSES.has(lifecycleStatus);
        if (claimsTerminal && !coherentTerminal) {
          failClosed("exception");
          return;
        }
        if (coherentTerminal) {
          completeResumePolling(context.selectedIds);
          return;
        }
        if (context.nextGateId && gates[context.nextGateId]?.status === "awaiting_approval") {
          completeResumePolling(context.selectedIds);
          return;
        }
        if (context.isLastGate) {
          const steps = state.steps || {};
          if (
            getRuntimeStatus(steps.audit) === "done"
            || getRuntimeStatus(steps.assemble_final) === "done"
          ) {
            completeResumePolling(context.selectedIds);
            return;
          }
        }

        const stateHash = JSON.stringify({
          current_step: currentStepName,
          gates: summarizeRuntimeStatuses(gates),
          steps: summarizeRuntimeStatuses(state.steps),
        });
        if (stateHash === lastStateHash) {
          stableCount += 1;
          if (stableCount >= 3) {
            failClosed("stalled");
            return;
          }
        } else {
          stableCount = 0;
          lastStateHash = stateHash;
        }

        pollTimerRef.current = setTimeout(
          () => poll(pollCount + 1),
          GATE_RESUME_INTERVAL_MS,
        );
      } catch (pollError: unknown) {
        console.error("GatePanel poll error:", pollError);
        failClosed("exception");
      }
    };

    pollTimerRef.current = setTimeout(() => poll(0), GATE_RESUME_INITIAL_DELAY_MS);
  }, [clearPollTimer, completeResumePolling, label, scenario]);

  // Cleanup poll timer on unmount
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      clearPollTimer();
    };
  }, [clearPollTimer]);

  const handleApprove = async () => {
    if (selectedIds.length === 0) return;
    setPollFailure(null);
    setApproving(true);

    // Demo mode: skip API, directly approve
    if (isDemoMode()) {
      setApproved(true);
      setTimeout(() => {
        onApprove(selectedIds);
      }, 800);
      setApproving(false);
      return;
    }

    try {
      const res = await apiFetch(
        `/scenario/${scenario}/gate/${label}/${gateId}/approve`,
        {
          method: "POST",
          body: JSON.stringify({ selected_ids: selectedIds }),
        }
      );
      if (!res.ok) {
        const errBody = await res.json().catch(() => ({}));
        throw new Error(errBody?.detail || `Approve failed (${res.status})`);
      }
      const approveResult = await res.json();

      // Backend is resuming in background. Poll for completion.
      if (approveResult.resuming) {
        setApproving(false);
        setProcessing(true);
        setLoadingText(t("gate.processing") || "Processing in background...");

        const seq = gateSequence || [];
        const currentIdx = seq.findIndex((g) => g.gateId === gateId);
        const nextGateId = currentIdx >= 0 && currentIdx + 1 < seq.length ? seq[currentIdx + 1].gateId : null;
        const isLastGate = currentIdx >= 0 && currentIdx + 1 === seq.length;

        startResumePolling({
          selectedIds: [...selectedIds],
          nextGateId,
          isLastGate,
        });
      } else {
        setApproved(true);
        setTimeout(() => {
          onApprove(selectedIds);
        }, 800);
      }
    } catch (e: unknown) {
      console.error("GatePanel approve error:", e);
      setError(errorMessage(e));
    } finally {
      setApproving(false);
    }
  };

  const retryResumePolling = () => {
    const context = resumePollingContextRef.current;
    if (context) startResumePolling(context);
  };

  // ── Progress indicator ──

  const progressLabel = `${t("app.step")} ${currentStep} / ${totalSteps}`;
  const continuityDisplay = normalizeContinuityDiagnostics(continuityDiagnostics);
  const showContinuityDiagnostics = hasContinuityDiagnostics(continuityDiagnostics);
  const continuitySummary = getContinuityDiagnosticsSummary(continuityDisplay, t);

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
            <h2 className="text-base font-semibold text-[var(--text-h1)]">
              {t(gateLabelKey)}
            </h2>
            <span className="text-[12px] text-[var(--text-body)] font-mono">
              {gateId.replace(/_/g, " ")}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[12px] text-[var(--text-body)] font-medium">
              {progressLabel}
            </span>
            {/* Progress dots */}
            <div className="flex gap-1">
              {Array.from({ length: totalSteps }, (_, i) => (
                <div
                  key={i}
                  className={`w-2 h-2 rounded-full ${
                    i + 1 < currentStep
                      ? "bg-[var(--jade-accent)]"
                      : i + 1 === currentStep
                      ? "bg-[var(--fortune-red)]"
                      : "bg-[var(--border-default)]"
                  }`}
                />
              ))}
            </div>
          </div>
        </div>
        {showContinuityDiagnostics && (
          <div className="mt-3 rounded-lg border border-[rgba(122,150,187,0.28)] bg-[rgba(122,150,187,0.10)] p-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[11px] font-medium text-[var(--cinema-azure)]">
                {t("continuity.diagnosticsTitle")}
              </span>
              {continuitySummary && (
                <span className="text-[11px] text-[var(--text-body)]">{continuitySummary}</span>
              )}
            </div>
            {continuityDisplay.clipDirections.length > 0 && (
              <div className="mt-2 space-y-1.5">
                {continuityDisplay.clipDirections.slice(0, 2).map((direction, index) => (
                  <div
                    key={`${direction.sceneBeat}-${direction.transitionIntent}-${index}`}
                    className="rounded-md bg-white/60 px-2.5 py-2 text-[11px] text-[var(--text-body)]"
                  >
                    <div className="font-medium text-[var(--text-h1)]">
                      {t("continuity.sceneBeatLabel")} {direction.sceneBeat || t("continuity.unknown")}
                    </div>
                    {direction.beatSummary && (
                      <div className="mt-0.5">
                        {t("continuity.beatSummaryLabel")}{" "}
                        <InlineTooltip
                          label={truncateDiagnosticText(direction.beatSummary)}
                          tooltip={direction.beatSummary}
                          className="max-w-[280px] align-top"
                          tooltipClassName="w-72"
                        />
                      </div>
                    )}
                    {direction.transitionIntent && (
                      <div className="mt-0.5">
                        {t("continuity.transitionIntentLabel")}{" "}
                        <InlineTooltip
                          label={truncateDiagnosticText(direction.transitionIntent)}
                          tooltip={direction.transitionIntent}
                          className="max-w-[280px] align-top"
                          tooltipClassName="w-72"
                        />
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Loading state */}
      {loading && (
        <div className="apple-card p-6">
          <div className="flex flex-col items-center gap-3 py-6">
            <div className="relative w-8 h-8">
              <svg className="animate-spin w-8 h-8" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="10" stroke="var(--border-default)" strokeWidth="3" />
                <path d="M12 2a10 10 0 0 1 10 10" stroke="var(--fortune-red)" strokeWidth="3" strokeLinecap="round" />
              </svg>
            </div>
            <p className="text-sm text-[var(--text-body)]">{loadingText}</p>
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
        <div className="apple-card p-6 border-l-4 border-[var(--crimson-mist)] bg-[rgba(196,91,80,0.08)]">
          <div className="flex items-start gap-3">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="shrink-0 mt-0.5">
              <circle cx="8" cy="8" r="7" stroke="var(--crimson-mist)" strokeWidth="1.2" />
              <line x1="8" y1="4.5" x2="8" y2="8.5" stroke="var(--crimson-mist)" strokeWidth="1.2" strokeLinecap="round" />
              <circle cx="8" cy="10.5" r="0.8" fill="var(--crimson-mist)" />
            </svg>
            <div className="flex-1">
              <p className="text-sm font-medium text-[var(--crimson-mist)] mb-1">
                {t("common.error")}
              </p>
              <p className="text-xs text-[var(--text-body)] mb-3">{error}</p>
              <div className="flex gap-2">
                <button
                  onClick={generateCandidates}
                  className="text-xs bg-[var(--crimson-mist)] text-white px-3 py-1.5 rounded-lg hover:bg-[var(--neon-red)] cursor-pointer"
                >
                  {t("step.retry")}
                </button>
                <button
                  onClick={onBack}
                  className="text-xs text-[var(--text-body)] px-3 py-1.5 rounded-lg hover:bg-[rgba(215,92,112,0.18)] cursor-pointer"
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
                  className="text-[12px] text-[var(--text-body)] hover:text-[var(--fortune-red)] transition-colors px-2 py-1 rounded hover:bg-[rgba(215,92,112,0.10)] disabled:opacity-50 cursor-pointer"
                >
                  {t("gate.regenerate")} {t(getVariantLabelKey(c.variant))}
                </button>
              ))}
            </div>
          )}

          {/* Edit panel placeholder */}
          {editCandidateId && (
            <div className="mt-3 p-3 rounded-lg bg-[var(--bg-card)] border border-[var(--border-default)]">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[12px] font-semibold text-[var(--text-h1)]">
                  {t("step.editTitle")} {editCandidateId}
                </span>
                <button
                  onClick={() => setEditCandidateId(null)}
                  className="text-[12px] text-[var(--text-body)] hover:text-[var(--text-h1)] cursor-pointer"
                >
                  {t("workflow.cancelEdit")}
                </button>
              </div>
              <pre className="text-[12px] font-mono text-[var(--text-body)] bg-[var(--bg-page)] p-2 rounded border border-[var(--border-default)] overflow-auto max-h-[200px] whitespace-pre-wrap break-all">
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
            <p className="text-[12px] text-[var(--text-muted)]">
              {selectedIds.length === 0
                ? t("gate.selectHint")
                : `${selectedIds.length}/${maxSelections} ${t("review.selected")}`}
            </p>
          </div>
        </div>
      )}

      {/* Approved / processing state */}
      {(approved || processing) && (
        <div className={`apple-card p-4 ${processing ? "border-[var(--cinema-azure)] bg-[rgba(122,150,187,0.10)]" : "border-[var(--fortune-red)] bg-[var(--bg-panel)]"}`}>
          <div className="flex items-center gap-2 justify-center">
            {processing ? (
              <>
                <div className="animate-spin w-4 h-4 border-2 border-[rgba(122,150,187,0.30)] border-t-[var(--cinema-azure)] rounded-full" />
                <span className="text-sm font-medium text-[var(--cinema-azure)]">
                  {t("gate.processing") || "Processing in background..."}
                </span>
              </>
            ) : (
              <>
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <circle cx="8" cy="8" r="7" fill="var(--fortune-red)" />
                  <path d="M5 8.5L7 10.5L11 5.5" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <span className="text-sm font-medium text-[var(--fortune-red)]">
                  {t("gate.approved") || "Approved, continuing..."}
                </span>
              </>
            )}
          </div>
        </div>
      )}

      {pollFailure && !processing && (
        <div className="apple-card p-4 border-l-4 border-[var(--gold-foil)]" role="alert">
          <p className="text-sm font-medium text-[var(--text-h1)]">
            {t(`gate.poll.${pollFailure}`)}
          </p>
          <button
            type="button"
            onClick={retryResumePolling}
            className="mt-3 apple-btn text-xs px-3 py-1.5 border border-[var(--border-default)]"
          >
            {t("gate.continueChecking")}
          </button>
        </div>
      )}

      {/* Action buttons */}
      {!loading && !error && !approved && !processing && !pollFailure && (
        <div className="flex items-center justify-between">
          <button
            onClick={onBack}
            disabled={approving}
            className="text-xs text-[var(--text-body)] px-4 py-2 rounded-lg hover:bg-[rgba(215,92,112,0.18)] transition-colors disabled:opacity-50 cursor-pointer"
          >
            {t("recommend.backToEdit")}
          </button>
          <button
            onClick={handleApprove}
            disabled={selectedIds.length === 0 || approving}
            className={`apple-btn text-xs px-5 py-2 disabled:opacity-50 ${
              selectedIds.length > 0
                ? "apple-btn-primary"
                : "bg-[var(--bg-panel)] text-[var(--text-muted)]"
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
