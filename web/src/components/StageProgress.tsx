"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import InlineTooltip from "@/components/InlineTooltip";
import { getScenarioStatus } from "./api";
import { useI18n } from "@/i18n/I18nProvider";
import {
  getContinuityDiagnosticsSummary,
  hasContinuityDiagnostics,
  normalizeContinuityDiagnostics,
  type ContinuityDiagnosticsPayload,
} from "@/lib/continuityDiagnostics";
import { truncateDiagnosticText } from "@/lib/diagnosticText";
import { normalizePipelineResult, normalizePipelineSteps } from "@/lib/pipelineResult";
import { getSoftDegradedSummary } from "@/lib/softDegraded";
import type { PipelineResult } from "@/stores/usePipelineStore";

interface Props {
  label: string;
  scenario: string;
  onComplete: (result: PipelineResult) => void;
  onGatePause?: (gateId: string | null) => void;
  onError?: (errors: string[]) => void;
  onRecoveryRequired?: () => void;
}

const POLL_FAILURE_THRESHOLD = 10;
const POLL_BASE_INTERVAL_MS = 2000;
const POLL_PAUSED_INTERVAL_MS = 10000;
const POLL_MAX_INTERVAL_MS = 30000;
const TERMINAL_SCENARIO_STATUSES = new Set(["completed", "completed_bounded", "completed_full"]);
const FAILED_SCENARIO_STATUSES = new Set(["error", "failed", "recovery_required"]);
const LIFECYCLE_RESULT_KEYS = [
  "status",
  "lifecycle_status",
  "completion_kind",
  "request_succeeded",
  "success",
  "full_media_success",
  "pipeline_complete",
  "publish_allowed",
  "delivery_accepted",
] as const;

// Per-scenario stage definitions (steps grouped into 3 narrative stages)
const SCENARIO_STAGES: Record<string, Array<{ id: string; label: string; narrative: string; steps: string[]; estimatedSeconds: number }>> = {
  s1: [
    { id: "writing", label: "stage.writing", narrative: "exec.narrative.analyzing",
      steps: ["strategy", "scripts", "compliance"], estimatedSeconds: 12 },
    { id: "visuals", label: "stage.visuals", narrative: "exec.narrative.visualizing",
      steps: ["storyboards", "keyframe_images", "video_prompts", "thumbnail_prompts", "seedance_clips"], estimatedSeconds: 370 },
    { id: "export", label: "stage.export", narrative: "exec.narrative.assembling",
      steps: ["tts_audio", "thumbnail_images", "assemble_final", "audit"], estimatedSeconds: 320 },
  ],
  s3: [
    { id: "writing", label: "stage.writing", narrative: "exec.narrative.analyzing",
      steps: ["video_analysis", "character_identity", "remix_script"], estimatedSeconds: 60 },
    { id: "visuals", label: "stage.visuals", narrative: "exec.narrative.visualizing",
      steps: ["storyboards", "keyframe_images", "video_prompts", "thumbnail_prompts", "seedance_clips"], estimatedSeconds: 370 },
    { id: "export", label: "stage.export", narrative: "exec.narrative.assembling",
      steps: ["tts_audio", "thumbnail_images", "assemble_final", "audit"], estimatedSeconds: 320 },
  ],
  s4: [
    { id: "writing", label: "stage.writing", narrative: "exec.narrative.analyzing",
      steps: ["scripts"], estimatedSeconds: 10 },
    { id: "visuals", label: "stage.visuals", narrative: "exec.narrative.visualizing",
      steps: ["video_prompts"], estimatedSeconds: 15 },
    { id: "export", label: "stage.export", narrative: "exec.narrative.assembling",
      steps: ["thumbnails"], estimatedSeconds: 10 },
  ],
  s5: [
    { id: "writing", label: "stage.writing", narrative: "exec.narrative.analyzing",
      steps: ["vlog_strategy", "video_prompts"], estimatedSeconds: 120 },
    { id: "visuals", label: "stage.visuals", narrative: "exec.narrative.visualizing",
      steps: ["seedance_clips"], estimatedSeconds: 300 },
    { id: "export", label: "stage.export", narrative: "exec.narrative.assembling",
      steps: ["tts_audio", "assemble_final", "audit"], estimatedSeconds: 200 },
  ],
};

// S2 reuses S1 stages
SCENARIO_STAGES.s2 = SCENARIO_STAGES.s1;

function getStages(scenario: string) {
  return SCENARIO_STAGES[scenario] || SCENARIO_STAGES.s1;
}

export function deriveCanonicalStageDefinitions(
  stageDefs: ReturnType<typeof getStages>,
  stepOrder: string[],
): ReturnType<typeof getStages> {
  if (stepOrder.length === 0) return stageDefs;

  const stageByStep = new Map<string, number>();
  stageDefs.forEach((stage, stageIndex) => {
    stage.steps.forEach((step) => stageByStep.set(step, stageIndex));
  });
  const nextSteps = stageDefs.map(() => [] as string[]);
  const fallbackStageIndex = Math.max(0, stageDefs.length - 1);
  for (const step of stepOrder) {
    const stageIndex = stageByStep.get(step) ?? fallbackStageIndex;
    nextSteps[stageIndex]?.push(step);
  }
  return stageDefs.map((stage, index) => ({ ...stage, steps: nextSteps[index] || [] }));
}

function getAverageDurationForStepType(
  stepName: string,
  steps: Record<string, Record<string, unknown>>,
  stageDefs: ReturnType<typeof getStages>,
): number | null {
  const sameStep = Object.entries(steps).filter(
    ([name, data]) =>
      name === stepName &&
      data?.status === "done" &&
      typeof data?.duration_ms === "number" &&
      data.duration_ms > 0,
  );
  if (sameStep.length > 0) {
    const avg = sameStep.reduce((sum, [, d]) => sum + (d.duration_ms as number), 0) / sameStep.length;
    return avg / 1000;
  }
  const stage = stageDefs.find((s) => s.steps.includes(stepName));
  if (!stage) return null;
  const stageDoneWithDuration = stage.steps
    .map((s) => steps[s])
    .filter((d): d is Record<string, unknown> => Boolean(d?.status === "done" && typeof d?.duration_ms === "number" && (d.duration_ms as number) > 0));
  if (stageDoneWithDuration.length > 0) {
    const avg = stageDoneWithDuration.reduce((sum, d) => sum + (d.duration_ms as number), 0) / stageDoneWithDuration.length;
    return avg / 1000;
  }
  return null;
}

function getStageProgress(stage: ReturnType<typeof getStages>[0], steps: Record<string, Record<string, unknown>>): number {
  const total = stage.steps.length;
  const done = stage.steps.filter((s) => steps[s]?.status === "done").length;
  return total === 0 ? 0 : Math.round((done / total) * 100);
}

type StageDefinition = ReturnType<typeof getStages>[number];
type StageRuntimeState = StageDefinition & {
  progress: number;
  allDone: boolean;
  anyStarted: boolean;
};

type CommercialInjectionSummary = {
  hard_token_ids?: unknown;
  soft_token_ids?: unknown;
  source_token_ids?: unknown;
  bundle_refs?: unknown;
  toolbox_refs?: unknown;
  contract_refs?: unknown;
  gate_checks?: unknown;
};

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function normalizeCommercialInjection(value: unknown): CommercialInjectionSummary | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as CommercialInjectionSummary : null;
}

export function deriveStageRuntimeState(
  stageDefs: StageDefinition[],
  steps: Record<string, Record<string, unknown>>,
): {
  stageStates: StageRuntimeState[];
  activeStageIdx: number;
  allComplete: boolean;
  stageCompletionKey: string;
} {
  const stageStates = stageDefs.map((stage) => {
    const progress = getStageProgress(stage, steps);
    const allDone = stage.steps.every((s) => steps[s]?.status === "done");
    const anyStarted = stage.steps.some((s) => steps[s]?.status && steps[s]?.status !== "pending");
    return { ...stage, progress, allDone, anyStarted };
  });
  const currentStageIdx = stageStates.findIndex((s) => !s.allDone && s.anyStarted);
  const activeStageIdx = currentStageIdx >= 0 ? currentStageIdx : (stageStates.every((s) => s.allDone) ? stageDefs.length - 1 : 0);
  const allComplete = stageStates.every((s) => s.allDone);
  const stageCompletionKey = stageStates.map((s) => (s.allDone ? "1" : "0")).join(",");
  return { stageStates, activeStageIdx, allComplete, stageCompletionKey };
}

export function estimateRemainingSeconds({
  allComplete,
  elapsed,
  stageDefs,
  steps,
}: {
  allComplete: boolean;
  elapsed: number;
  stageDefs: StageDefinition[];
  steps: Record<string, Record<string, unknown>>;
}): number | null {
  if (allComplete) return 0;
  if (elapsed < 5) return null;

  let completedActual = 0;
  let completedFallback = 0;
  let remainingEstimate = 0;

  for (const stage of stageDefs) {
    for (const st of stage.steps) {
      const stepData = steps[st];
      const isDone = stepData?.status === "done";
      const durationMs = typeof stepData?.duration_ms === "number" ? stepData.duration_ms : 0;
      const hasDuration = durationMs > 0;

      if (isDone) {
        if (hasDuration) {
          completedActual += durationMs / 1000;
        } else {
          completedFallback += stage.estimatedSeconds / stage.steps.length;
        }
      } else {
        const sameTypeAvg = getAverageDurationForStepType(st, steps, stageDefs);
        remainingEstimate += sameTypeAvg || (stage.estimatedSeconds / stage.steps.length);
      }
    }
  }

  const completedTotal = completedActual + completedFallback;
  if (completedTotal <= 0) return null;
  const pace = elapsed / completedTotal;
  const remaining = Math.round(remainingEstimate * pace);
  return Math.max(remaining, 0);
}

export function deriveTotalProgress(
  stageDefs: StageDefinition[],
  steps: Record<string, Record<string, unknown>>,
): {
  totalSteps: number;
  totalDone: number;
  totalProgress: number;
} {
  const totalSteps = stageDefs.reduce((sum, s) => sum + s.steps.length, 0);
  const totalDone = stageDefs.reduce((sum, s) => sum + s.steps.filter((st) => steps[st]?.status === "done").length, 0);
  const totalProgress = totalSteps === 0 ? 0 : Math.round((totalDone / totalSteps) * 100);
  return { totalSteps, totalDone, totalProgress };
}

function getStageStatus(
  stageId: string,
  steps: Record<string, Record<string, unknown>>,
  t: (key: string) => string,
  stageDefs: ReturnType<typeof getStages>,
  narrativeKey?: string,
): string {
  if (narrativeKey) {
    const stage = stageDefs.find((s) => s.id === stageId);
    if (stage?.narrative) return t(stage.narrative);
  }
  if (stageId === "writing") {
    if (steps.scripts?.status === "done" || steps.remix_script?.status === "done") return t("stage.substatus.scriptComplete");
    if (steps.strategy?.status === "done" || steps.vlog_strategy?.status === "done") return t("stage.substatus.generatingScripts");
    if (steps.video_analysis?.status === "done") return t("stage.substatus.generatingScripts");
    return t("stage.substatus.analyzing");
  }
  if (stageId === "visuals") {
    if (steps.seedance_clips?.status === "done") return t("stage.substatus.clipsComplete");
    if (steps.video_prompts?.status === "done") return t("stage.substatus.creatingClips");
    if (steps.storyboards?.status === "done") return t("stage.substatus.designingStoryboard");
    return t("stage.substatus.designingStoryboard");
  }
  if (stageId === "export") {
    if (steps.audit?.status === "done") return t("stage.substatus.exportComplete");
    if (steps.assemble_final?.status === "done") return t("stage.substatus.runningAudit");
    if (steps.thumbnails?.status === "done") return t("stage.substatus.exportComplete");
    return t("stage.substatus.assembling");
  }
  return "";
}

export default function StageProgress({
  label,
  scenario,
  onComplete,
  onGatePause,
  onError,
  onRecoveryRequired,
}: Props) {
  const { t } = useI18n();
  const [canonicalStepOrder, setCanonicalStepOrder] = useState<string[]>([]);
  const stageDefs = deriveCanonicalStageDefinitions(getStages(scenario), canonicalStepOrder);

  const [steps, setSteps] = useState<Record<string, Record<string, unknown>>>({});
  const [status, setStatus] = useState<string>("running");
  const [gateStatus, setGateStatus] = useState<string | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [currentStepInjection, setCurrentStepInjection] = useState<CommercialInjectionSummary | null>(null);
  const [softDegradedReasons, setSoftDegradedReasons] = useState<Array<{ step?: string; reason?: string; detail?: string }>>([]);
  const [continuityDiagnostics, setContinuityDiagnostics] = useState<ContinuityDiagnosticsPayload | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const completedRef = useRef(false);
  const mountedRef = useRef(true);
  const celebrationTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const completionTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const notifiedErrorSignatureRef = useRef<string | null>(null);
  const notifiedGatePauseSignatureRef = useRef<string | null>(null);

  // P1-6: Exponential backoff for polling
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const failureCountRef = useRef(0);
  const [pollError, setPollError] = useState<string | null>(null);
  const [pollRetryNonce, setPollRetryNonce] = useState(0);

  const prevCompleteRef = useRef<boolean[]>([false, false, false]);
  const [celebrations, setCelebrations] = useState<boolean[]>([false, false, false]);

  const { stageStates, activeStageIdx, allComplete, stageCompletionKey } = deriveStageRuntimeState(stageDefs, steps);

  const clearPollTimeout = useCallback(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
  }, []);

  const stopElapsedTimer = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const clearCelebrationTimeout = useCallback(() => {
    if (celebrationTimeoutRef.current) {
      clearTimeout(celebrationTimeoutRef.current);
      celebrationTimeoutRef.current = null;
    }
  }, []);

  const clearCompletionTimeout = useCallback(() => {
    if (completionTimeoutRef.current) {
      clearTimeout(completionTimeoutRef.current);
      completionTimeoutRef.current = null;
    }
  }, []);

  const clearStageTimers = useCallback(() => {
    clearPollTimeout();
    stopElapsedTimer();
    clearCelebrationTimeout();
    clearCompletionTimeout();
  }, [clearCelebrationTimeout, clearCompletionTimeout, clearPollTimeout, stopElapsedTimer]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      clearStageTimers();
    };
  }, [clearStageTimers]);

  // Trigger celebration animation when a stage completes
  useEffect(() => {
    const newComplete = stageCompletionKey.split(",").map((value) => value === "1");
    const prevComplete = prevCompleteRef.current;
    const triggered = newComplete.map((c, i) => c && !prevComplete[i]);
    if (triggered.some(Boolean)) {
      setCelebrations(triggered);
      clearCelebrationTimeout();
      celebrationTimeoutRef.current = setTimeout(() => {
        if (mountedRef.current) setCelebrations([false, false, false]);
      }, 1200);
    }
    prevCompleteRef.current = newComplete;
  }, [clearCelebrationTimeout, stageCompletionKey]);

  // Elapsed time counter
  useEffect(() => {
    timerRef.current = setInterval(() => {
      setElapsed((prev) => prev + 1);
    }, 1000);
    return () => {
      stopElapsedTimer();
    };
  }, [stopElapsedTimer]);

  // Polling with exponential backoff
  // Use ref for self-reference (react-hooks/no-use-before-define safe)
  const pollRef = useRef<() => Promise<void>>(() => Promise.resolve());
  const poll = useCallback(async () => {
    if (!mountedRef.current || completedRef.current || pollError) return;
    clearPollTimeout();
    let nextPollIntervalMs = POLL_BASE_INTERVAL_MS;

    try {
      const data = await getScenarioStatus(scenario, label);
      if (!mountedRef.current) return;
      failureCountRef.current = 0;
      setPollError(null);

      const newSteps = normalizePipelineSteps(data.steps);
      setSteps(newSteps);
      setCanonicalStepOrder(
        Array.isArray(data.step_order)
          ? Array.from(new Set(data.step_order.filter((step): step is string => typeof step === "string" && step.length > 0)))
          : [],
      );
      const lifecycleFailure = typeof data.lifecycle_status === "string"
        && FAILED_SCENARIO_STATUSES.has(data.lifecycle_status)
        ? data.lifecycle_status
        : null;
      setStatus(lifecycleFailure ?? data.status);
      setGateStatus(data.gate_status);
      setCurrentStepInjection(normalizeCommercialInjection(data.current_step_injection));
      const currentErrors = data.errors || [];
      const isServerError = FAILED_SCENARIO_STATUSES.has(data.status)
        || lifecycleFailure !== null
        || Boolean(data.pipeline_degraded);
      const isRecoveryRequired = data.status === "recovery_required"
        || data.lifecycle_status === "recovery_required";
      const effectiveErrors = currentErrors.length > 0
        ? currentErrors
        : isServerError && !isRecoveryRequired
          ? ["scenario_execution_failed"]
          : [];
      setErrors(effectiveErrors);
      setSoftDegradedReasons(data.soft_degraded_reasons || []);
      setContinuityDiagnostics(data.continuity_diagnostics || null);

      if (isRecoveryRequired) {
        clearPollTimeout();
        stopElapsedTimer();
        onRecoveryRequired?.();
        return;
      }

      const gatePauseSignature =
        data.status === "paused" && data.gate_status === "awaiting_approval"
          ? data.current_step || "unknown"
          : null;
      if (gatePauseSignature) {
        nextPollIntervalMs = POLL_PAUSED_INTERVAL_MS;
      }

      // Notify parent of gate pause
      if (gatePauseSignature && onGatePause) {
        if (notifiedGatePauseSignatureRef.current !== gatePauseSignature) {
          notifiedGatePauseSignatureRef.current = gatePauseSignature;
          onGatePause(data.current_step);
        }
      } else if (!gatePauseSignature) {
        notifiedGatePauseSignatureRef.current = null;
      }

      // Notify parent of error
      if (isServerError && onError && effectiveErrors.length > 0) {
        const errorSignature = effectiveErrors.join("\n");
        if (notifiedErrorSignatureRef.current !== errorSignature) {
          notifiedErrorSignatureRef.current = errorSignature;
          onError(effectiveErrors);
        }
      } else if (!isServerError) {
        notifiedErrorSignatureRef.current = null;
      }

      // Check completion
      const isTerminalStatus = TERMINAL_SCENARIO_STATUSES.has(data.status)
        || (typeof data.lifecycle_status === "string"
          && TERMINAL_SCENARIO_STATUSES.has(data.lifecycle_status));
      if (isTerminalStatus && !completedRef.current) {
        completedRef.current = true;
        clearPollTimeout();
        stopElapsedTimer();
        completionTimeoutRef.current = setTimeout(() => {
          if (!mountedRef.current) return;
          const result = normalizePipelineResult(data.result || newSteps);
          if (isTerminalStatus) {
            for (const key of LIFECYCLE_RESULT_KEYS) {
              const value = data[key];
              if (value !== undefined) result[key] = value;
            }
            result.resource_type = "scenario";
            result.resource_id = label;
          }
          onComplete(result);
        }, 1500);
        return;
      }

      // Check error — stop polling but don't call onComplete
      if (isServerError) {
        stopElapsedTimer();
        return;
      }
    } catch {
      if (!mountedRef.current) return;
      failureCountRef.current += 1;
      if (failureCountRef.current >= POLL_FAILURE_THRESHOLD) {
        clearPollTimeout();
        setPollError(t("stage.pollingError") || "Connection lost. Please refresh to retry.");
        return;
      }
      nextPollIntervalMs = Math.min(
        POLL_BASE_INTERVAL_MS * Math.pow(2, failureCountRef.current),
        POLL_MAX_INTERVAL_MS
      );
    }

    if (!mountedRef.current) return;
    timeoutRef.current = setTimeout(() => pollRef.current(), nextPollIntervalMs);
  }, [
    clearPollTimeout,
    label,
    onComplete,
    onError,
    onGatePause,
    onRecoveryRequired,
    pollError,
    scenario,
    stopElapsedTimer,
    t,
  ]);

  // Keep ref synced with latest poll callback.
  useEffect(() => {
    pollRef.current = poll;
  }, [poll]);

  useEffect(() => {
    timeoutRef.current = setTimeout(() => pollRef.current(), POLL_BASE_INTERVAL_MS);
    return () => {
      clearPollTimeout();
    };
  }, [clearPollTimeout, pollRetryNonce]);

  const continuePolling = useCallback(() => {
    clearPollTimeout();
    failureCountRef.current = 0;
    setPollError(null);
    setPollRetryNonce((value) => value + 1);
  }, [clearPollTimeout]);

  const formatTime = (seconds: number): string => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  };

  const estimatedRemaining = estimateRemainingSeconds({ allComplete, elapsed, stageDefs, steps });

  const { totalSteps, totalDone, totalProgress } = deriveTotalProgress(stageDefs, steps);

  const isError = FAILED_SCENARIO_STATUSES.has(status) || errors.length > 0;
  const isPaused = status === "paused";
  const softDegradedSummary = softDegradedReasons[0];
  const softDegradedDisplay = getSoftDegradedSummary(softDegradedSummary, t);
  const continuityDisplay = normalizeContinuityDiagnostics(continuityDiagnostics);
  const showContinuityDiagnostics = hasContinuityDiagnostics(continuityDiagnostics);
  const continuitySummary = getContinuityDiagnosticsSummary(continuityDisplay, t);

  return (
    <div className="apple-card p-6 space-y-5 relative overflow-hidden">
      {/* Completion celebration */}
      {allComplete && (
        <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
          <div className="absolute inset-0 bg-gradient-to-b from-[rgba(110,150,110,0.08)] via-transparent to-transparent animate-pulse" />
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="relative w-3 h-3">
            <div
              className={`absolute inset-0 rounded-full transition-all duration-1000 ${
                allComplete
                  ? "bg-[var(--jade-accent)]"
                  : isError
                  ? "bg-red-500"
                  : isPaused
                  ? "bg-amber-500"
                  : "bg-[var(--fortune-red)]"
              }`}
              style={{
                animation: allComplete
                  ? "stagePulse 0.8s ease-in-out 3"
                  : stageStates[activeStageIdx]?.anyStarted && !isError && !isPaused
                  ? "stageBreathe 2s ease-in-out infinite"
                  : "none",
              }}
            />
            {stageStates[activeStageIdx]?.anyStarted && !allComplete && !isError && !isPaused && (
              <div
                className="absolute inset-0 rounded-full bg-[rgba(215,92,112,0.30)]"
                style={{ animation: "stageRipple 2s ease-out infinite" }}
              />
            )}
          </div>
          <div>
            <h3 className="text-sm font-semibold text-[var(--text-h1)] leading-tight">
              {allComplete ? t("pipeline.allDone") : isError ? t("pipeline.error") || "Error" : isPaused ? t("pipeline.paused") || "Paused" : t("mode.smartCreate")}
            </h3>
            {!allComplete && (
              <p className="text-[11px] text-[var(--text-muted)] leading-tight">
                {totalProgress}% &middot; {stageStates.filter((s) => s.allDone).length}/{stageDefs.length} {t("step.items")}
              </p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[11px] uppercase tracking-widest text-[var(--text-muted)] font-medium">
            {allComplete ? t("stage.export") : t("stage.elapsed")}
          </span>
          <span className="text-sm font-mono font-semibold text-[var(--text-h1)] tabular-nums">
            {formatTime(elapsed)}
          </span>
        </div>
      </div>

      {/* Gate pause banner */}
      {isPaused && gateStatus === "awaiting_approval" && (
        <div className="p-2.5 rounded-lg bg-amber-50 border border-amber-200">
          <p className="text-[11px] text-amber-800 flex items-center gap-1.5">
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" className="shrink-0">
              <path d="M6 2v4M6 8v.5" stroke="currentColor" strokeLinecap="round" />
            </svg>
            {t("gate.awaitingApproval") || "Awaiting approval — please review candidates in Expert Studio"}
          </p>
        </div>
      )}

      {currentStepInjection && !isError && (
        <CurrentCommercialInjectionSummary injection={currentStepInjection} />
      )}

      {softDegradedReasons.length > 0 && !isError && (
        <div className="p-2.5 rounded-lg bg-amber-50 border border-amber-200">
          <p className="text-[11px] text-amber-800 flex items-center gap-1.5">
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" className="shrink-0">
              <circle cx="6" cy="6" r="5.5" stroke="currentColor" />
              <path d="M6 3.5v3M6 8v.5" stroke="currentColor" strokeLinecap="round" />
            </svg>
            {t("degraded.softTitle")}
            {softDegradedDisplay.stepLabel ? ` · ${softDegradedDisplay.stepLabel}` : ""}
            {softDegradedDisplay.reasonLabel ? ` · ${softDegradedDisplay.reasonLabel}` : ""}
          </p>
          {softDegradedDisplay.detail ? (
            <p className="mt-1 text-[11px] text-amber-700">{softDegradedDisplay.detail}</p>
          ) : null}
        </div>
      )}

      {showContinuityDiagnostics && !isError && (
        <div className="p-3 rounded-lg border border-[rgba(122,150,187,0.28)] bg-[rgba(122,150,187,0.10)]">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-[11px] text-[var(--cinema-azure)] font-medium">
              {t("continuity.diagnosticsTitle")}
            </p>
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

      {/* Error banner */}
      {isError && errors.length > 0 && (
        <div className="p-2.5 rounded-lg bg-red-50 border border-red-200">
          <p className="text-[11px] text-red-700 flex items-center gap-1.5">
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" className="shrink-0">
              <circle cx="6" cy="6" r="5.5" stroke="currentColor" />
              <path d="M6 3.5v3M6 8v.5" stroke="currentColor" strokeLinecap="round" />
            </svg>
            {errors[0]}
          </p>
        </div>
      )}

      {/* Animated pipeline */}
      <div className="relative">
        <div className="absolute left-[11px] top-3 bottom-3 w-1 rounded-full bg-[var(--border-default)]" />
        <div
          className="absolute left-[11px] top-3 w-1 rounded-full transition-all duration-1000 ease-out"
          style={{
            height: `${allComplete ? 100 : Math.min((totalDone / totalSteps) * 100, 100)}%`,
            background: isError
              ? "linear-gradient(to bottom, #ef4444, #b91c1c)"
              : "linear-gradient(to bottom, var(--fortune-red), var(--neon-red), var(--cinema-azure))",
            opacity: totalDone > 0 ? 1 : 0,
          }}
        />
        <div className="space-y-5">
          {stageDefs.map((stage, idx) => {
            const isActive = idx === activeStageIdx && !allComplete;
            const isComplete = stageStates[idx].allDone;
            const isWaiting = !stageStates[idx].anyStarted && !isComplete;
            const progress = stageStates[idx].progress;
            const statusText = getStageStatus(stage.id, steps, t, stageDefs, stage.narrative);
            const celebrating = celebrations[idx];

            return (
              <div key={stage.id} className="relative pl-10">
                <div className="absolute left-[8px] top-2 z-10">
                  <div
                    className={`w-[7px] h-[7px] rounded-full transition-all duration-500 ${
                      isComplete
                        ? "bg-[var(--jade-accent)] shadow-[0_0_6px_rgba(110,150,110,0.6)]"
                        : isActive
                        ? isError
                          ? "bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.6)]"
                          : "bg-[var(--fortune-red)] shadow-[0_0_8px_rgba(215,92,112,0.6)]"
                        : "bg-[var(--border-default)]"
                    } ${celebrating ? "animate-[stagePop_0.5s_ease-out]" : ""}`}
                  />
                  {celebrating && (
                    <div
                      className="absolute inset-0 rounded-full bg-[rgba(110,150,110,0.40)]"
                      style={{ animation: "stageRipple 0.8s ease-out forwards", transform: "scale(1)" }}
                    />
                  )}
                </div>

                <div className={`transition-opacity duration-500 ${isWaiting ? "opacity-40" : "opacity-100"}`}>
                  <div className="flex items-center gap-2 mb-1.5">
                    <StageIcon
                      stageId={stage.id}
                      active={isActive}
                      complete={isComplete}
                      celebrating={celebrating}
                      error={isError}
                    />
                    <span
                      className={`text-[13px] font-medium transition-colors duration-500 ${
                        isComplete
                          ? "text-[var(--text-h1)]"
                          : isActive
                          ? isError
                            ? "text-red-500"
                            : "text-[var(--fortune-red)]"
                          : "text-[var(--text-muted)]"
                      }`}
                    >
                      {t(stage.label)}
                    </span>
                    {isComplete && (
                      <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="shrink-0"
                        style={{ animation: celebrating ? "stagePop 0.5s ease-out" : "none" }}>
                        <path d="M3 7.5L5.5 10L11 4" stroke="var(--jade-accent)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    )}
                  </div>

                  <div className="ml-0 space-y-1.5">
                    {isComplete && !isActive && (
                      <p className="text-[11px] text-[var(--text-body)] italic">
                        {stage.steps.filter((s) => steps[s]?.status === "done").length} {t("step.items")} &middot; {t("stage.completed")}
                      </p>
                    )}
                    {isActive && (
                      <>
                        <p className="text-[11px] text-[var(--text-body)]">{statusText}</p>
                        <div className="h-1.5 w-full bg-[var(--bg-panel)] rounded-full overflow-hidden">
                          <div
                            className="h-full rounded-full transition-all duration-1000 ease-out"
                            style={{
                              width: `${progress}%`,
                              background: isError
                                ? "linear-gradient(to right, #ef4444, #b91c1c)"
                                : stage.id === "writing"
                                ? "linear-gradient(to right, var(--gold-foil), var(--fortune-red))"
                                : stage.id === "visuals"
                                ? "linear-gradient(to right, var(--fortune-red), var(--neon-red), var(--cinema-azure))"
                                : "linear-gradient(to right, var(--cinema-azure), var(--fortune-red))",
                            }}
                          />
                        </div>
                        <div className="flex justify-between text-[11px]">
                          <span className="text-[var(--text-muted)]">
                            {stage.steps.filter((s) => steps[s]?.status === "done").length}/{stage.steps.length}
                          </span>
                          <span
                            className="font-mono font-medium"
                            style={{
                              color: isError
                                ? "#ef4444"
                                : stage.id === "writing"
                                ? "var(--gold-foil)"
                                : stage.id === "visuals"
                                ? "var(--cinema-azure)"
                                : "var(--fortune-red)",
                            }}
                          >
                            {progress}%
                          </span>
                        </div>
                      </>
                    )}
                    {isWaiting && (
                      <p className="text-[11px] text-[var(--text-muted)] italic">{t("stage.waiting")}</p>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between pt-3 border-t border-[var(--border-default)]">
        <span className="text-[11px] text-[var(--text-muted)]">
          {t("stage.elapsed")}: {formatTime(elapsed)}
        </span>
        {estimatedRemaining !== null && !allComplete && !pollError && !isError && (
          <span className="text-[11px] text-[var(--text-body)]">
            {t("stage.estimatedTime")}: ~{formatTime(estimatedRemaining)}
          </span>
        )}
        {allComplete && (
          <span className="text-[11px] font-medium text-[var(--jade-accent)]">
            {t("pipeline.allDone")} &middot; {formatTime(elapsed)}
          </span>
        )}
      </div>

      {/* Polling error banner */}
      {pollError && (
        <div className="mt-3 p-2.5 rounded-lg bg-red-50 border border-red-200">
          <p className="text-[11px] text-red-700 flex items-center gap-1.5">
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" className="shrink-0">
              <circle cx="6" cy="6" r="5.5" stroke="currentColor" />
              <path d="M6 3.5v3M6 8v.5" stroke="currentColor" strokeLinecap="round" />
            </svg>
            {pollError}
          </p>
          <button
            type="button"
            onClick={continuePolling}
            className="mt-2 text-[11px] font-medium text-red-700 underline"
          >
            {t("submission.continueChecking")}
          </button>
        </div>
      )}

      <style jsx>{`
        @keyframes stageBreathe {
          0%, 100% { transform: scale(1); opacity: 1; }
          50% { transform: scale(1.6); opacity: 0.5; }
        }
        @keyframes stageRipple {
          0% { transform: scale(1); opacity: 0.5; }
          100% { transform: scale(4); opacity: 0; }
        }
        @keyframes stagePop {
          0% { transform: scale(1); }
          50% { transform: scale(1.8); }
          100% { transform: scale(1); }
        }
      `}</style>
    </div>
  );
}

// ═══ Stage Icon — visual metaphors per stage ═══

function CurrentCommercialInjectionSummary({ injection }: { injection: CommercialInjectionSummary }) {
  const { t } = useI18n();
  const groups = [
    { label: t("commercialInjection.bundle"), values: stringList(injection.bundle_refs) },
    { label: t("commercialInjection.toolbox"), values: stringList(injection.toolbox_refs) },
    { label: t("commercialInjection.contract"), values: stringList(injection.contract_refs) },
    { label: t("commercialInjection.gate"), values: stringList(injection.gate_checks) },
    {
      label: t("commercialInjection.tokens"),
      values: [
        ...stringList(injection.hard_token_ids),
        ...stringList(injection.soft_token_ids),
        ...stringList(injection.source_token_ids),
      ],
    },
  ].filter((group) => group.values.length > 0);

  if (groups.length === 0) return null;

  return (
    <div className="rounded-lg border border-[rgba(220,190,120,0.24)] bg-[rgba(220,190,120,0.07)] px-3 py-2">
      <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
        <span className="text-[11px] font-semibold text-[var(--gold-foil)]">
          {t("commercialInjection.currentStep")}
        </span>
        <span className="rounded-full bg-[rgba(220,190,120,0.12)] px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.02em] text-[var(--text-muted)]">
          {t("commercialInjection.readOnly")}
        </span>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {groups.map((group) => (
          <div key={group.label} className="flex min-w-0 max-w-full items-center gap-1">
            <span className="text-[11px] font-semibold uppercase tracking-[0.02em] text-[var(--text-muted)]">
              {group.label}
            </span>
            <div className="flex min-w-0 flex-wrap gap-1">
              {group.values.slice(0, 3).map((value) => (
                <span
                  key={`${group.label}-${value}`}
                  className="max-w-[160px] truncate rounded-md bg-[var(--bg-panel)] px-1.5 py-0.5 text-[11px] font-medium text-[var(--text-h1)]"
                  title={value}
                >
                  {value}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function StageIcon({
  stageId,
  active,
  complete,
  celebrating,
  error,
}: {
  stageId: string;
  active: boolean;
  complete: boolean;
  celebrating: boolean;
  error?: boolean;
}) {
  const color = error ? "#ef4444" : complete ? "var(--jade-accent)" : active ? "var(--fortune-red)" : "var(--text-muted)";
  const size = 16;

  if (stageId === "writing") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="shrink-0"
        style={{ animation: active ? "stageBreathe 2s ease-in-out infinite" : celebrating ? "stagePop 0.5s ease-out" : "none" }}>
        <path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
        <path d="M15 5c1.5 1.5 3 3 4 4" opacity="0.5" />
      </svg>
    );
  }

  if (stageId === "visuals") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="shrink-0"
        style={{ animation: active ? "stageBreathRotate 3s ease-in-out infinite" : celebrating ? "stagePop 0.5s ease-out" : "none" }}>
        <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
        <circle cx="12" cy="13" r="4" />
        {active && (<><path d="M12 9v8" opacity="0.3" /><path d="M9 12h6" opacity="0.3" /></>)}
      </svg>
    );
  }

  if (stageId === "export") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="shrink-0"
        style={{ animation: active ? "stageBreathe 2s ease-in-out infinite" : celebrating ? "stagePop 0.5s ease-out" : "none" }}>
        <rect x="2" y="4" width="20" height="16" rx="2" />
        <line x1="2" y1="8" x2="22" y2="8" opacity="0.4" />
        <line x1="2" y1="16" x2="22" y2="16" opacity="0.4" />
        <rect x="4" y="9" width="3" height="6" rx="0.5" opacity={complete ? "0.8" : "0.3"} />
        <rect x="8" y="9" width="3" height="6" rx="0.5" opacity={active || complete ? "0.8" : "0.2"} />
        <rect x="12" y="9" width="3" height="6" rx="0.5" opacity={complete ? "0.8" : "0.2"} />
      </svg>
    );
  }

  return null;
}
