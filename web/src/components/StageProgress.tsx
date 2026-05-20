"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { getScenarioStatus } from "./api";
import { useI18n } from "@/i18n/I18nProvider";

interface Props {
  label: string;
  scenario: string;
  onComplete: (result: unknown) => void;
  onGatePause?: (gateId: string | null) => void;
  onError?: (errors: string[]) => void;
}

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

export default function StageProgress({ label, scenario, onComplete, onGatePause, onError }: Props) {
  const { t } = useI18n();
  const STAGES = getStages(scenario);

  const [steps, setSteps] = useState<Record<string, Record<string, unknown>>>({});
  const [status, setStatus] = useState<string>("running");
  const [gateStatus, setGateStatus] = useState<string | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [elapsed, setElapsed] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const completedRef = useRef(false);

  // P1-6: Exponential backoff for polling
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const failureCountRef = useRef(0);
  const POLL_FAILURE_THRESHOLD = 10;
  const POLL_BASE_INTERVAL_MS = 2000;
  const POLL_MAX_INTERVAL_MS = 30000;
  const [pollError, setPollError] = useState<string | null>(null);

  const [prevComplete, setPrevComplete] = useState<boolean[]>([false, false, false]);
  const [celebrations, setCelebrations] = useState<boolean[]>([false, false, false]);

  const stageStates = STAGES.map((stage) => {
    const progress = getStageProgress(stage, steps);
    const allDone = stage.steps.every((s) => steps[s]?.status === "done");
    const anyStarted = stage.steps.some((s) => steps[s]?.status && steps[s]?.status !== "pending");
    return { ...stage, progress, allDone, anyStarted };
  });

  const currentStageIdx = stageStates.findIndex((s) => !s.allDone && s.anyStarted);
  const activeStageIdx = currentStageIdx >= 0 ? currentStageIdx : (stageStates.every((s) => s.allDone) ? STAGES.length - 1 : 0);
  const allComplete = stageStates.every((s) => s.allDone);

  // Trigger celebration animation when a stage completes
  useEffect(() => {
    const newComplete = stageStates.map((s) => s.allDone);
    const triggered = newComplete.map((c, i) => c && !prevComplete[i]);
    if (triggered.some(Boolean)) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setCelebrations(triggered);
      setTimeout(() => setCelebrations([false, false, false]), 1200);
    }
    setPrevComplete(newComplete);
  }, [stageStates.map((s) => s.allDone).join(",")]);

  // Elapsed time counter
  useEffect(() => {
    timerRef.current = setInterval(() => {
      setElapsed((prev) => prev + 1);
    }, 1000);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  // Polling with exponential backoff
  // Use ref for self-reference (react-hooks/no-use-before-define safe)
  const pollRef = useRef<() => Promise<void>>(() => Promise.resolve());
  // eslint-disable-next-line react-hooks/preserve-manual-memoization
  const poll = useCallback(async () => {
    if (completedRef.current || pollError) return;

    try {
      const data = await getScenarioStatus(scenario, label);
      failureCountRef.current = 0;
      setPollError(null);

      const newSteps = (data.steps as Record<string, Record<string, unknown>>) || {};
      setSteps(newSteps);
      setStatus(data.status);
      setGateStatus(data.gate_status);
      setErrors(data.errors || []);

      // Notify parent of gate pause
      if (data.status === "paused" && data.gate_status === "awaiting_approval" && onGatePause) {
        onGatePause(data.current_step);
      }

      // Notify parent of error
      if ((data.status === "error" || data.pipeline_degraded) && onError && (data.errors || []).length > 0) {
        onError(data.errors);
      }

      // Check completion
      const allDone = STAGES.every((stage) =>
        stage.steps.every((s) => newSteps[s]?.status === "done")
      );
      if ((allDone || data.status === "completed") && !completedRef.current) {
        completedRef.current = true;
        if (timeoutRef.current) clearTimeout(timeoutRef.current);
        if (timerRef.current) clearInterval(timerRef.current);
        setTimeout(() => onComplete(data.result || newSteps), 1500);
        return;
      }

      // Check error — stop polling but don't call onComplete
      if (data.status === "error" || data.pipeline_degraded) {
        // Keep polling for recovery? No — stop and show error banner
        // But don't clear timeout so the error banner stays visible
        return;
      }
    } catch {
      failureCountRef.current += 1;
      if (failureCountRef.current >= POLL_FAILURE_THRESHOLD) {
        setPollError(t("stage.pollingError") || "Connection lost. Please refresh to retry.");
        return;
      }
    }

    const backoffMs = Math.min(
      POLL_BASE_INTERVAL_MS * Math.pow(2, failureCountRef.current),
      POLL_MAX_INTERVAL_MS
    );
    timeoutRef.current = setTimeout(() => pollRef.current(), backoffMs);
  }, [label, scenario, onComplete, onGatePause, onError, pollError, t, STAGES]);

  // Keep ref synced with latest poll callback.
  useEffect(() => {
    pollRef.current = poll;
  }, [poll]);

  useEffect(() => {
    timeoutRef.current = setTimeout(poll, POLL_BASE_INTERVAL_MS);
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const formatTime = (seconds: number): string => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  };

  const estimatedRemaining = (() => {
    if (allComplete) return 0;
    if (elapsed < 5) return null;

    let completedActual = 0;
    let completedFallback = 0;
    let remainingEstimate = 0;

    for (const stage of STAGES) {
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
          const sameTypeAvg = getAverageDurationForStepType(st, steps, STAGES);
          remainingEstimate += sameTypeAvg || (stage.estimatedSeconds / stage.steps.length);
        }
      }
    }

    const completedTotal = completedActual + completedFallback;
    if (completedTotal <= 0) return null;
    const pace = elapsed / completedTotal;
    const remaining = Math.round(remainingEstimate * pace);
    return Math.max(remaining, 0);
  })();

  const totalSteps = STAGES.reduce((sum, s) => sum + s.steps.length, 0);
  const totalDone = STAGES.reduce((sum, s) => sum + s.steps.filter((st) => steps[st]?.status === "done").length, 0);
  const totalProgress = totalSteps === 0 ? 0 : Math.round((totalDone / totalSteps) * 100);

  const isError = status === "error" || errors.length > 0;
  const isPaused = status === "paused";

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
                {totalProgress}% &middot; {stageStates.filter((s) => s.allDone).length}/{STAGES.length} {t("step.items")}
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
          {STAGES.map((stage, idx) => {
            const isActive = idx === activeStageIdx && !allComplete;
            const isComplete = stageStates[idx].allDone;
            const isWaiting = !stageStates[idx].anyStarted && !isComplete;
            const progress = stageStates[idx].progress;
            const statusText = getStageStatus(stage.id, steps, t, STAGES, stage.narrative);
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
