"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { fetchS1State } from "./api";
import { useI18n } from "@/i18n/I18nProvider";

interface Props {
  label: string;
  onComplete: (result: any) => void;
}

// Stage weights based on actual poyo.ai API timing (seconds)
// writing: ~12s total | visuals: ~370s (mostly seedance) | export: ~320s
const STAGES = [
  {
    id: "writing",
    label: "stage.writing",
    steps: ["strategy", "scripts", "compliance"],
    estimatedSeconds: 12,
  },
  {
    id: "visuals",
    label: "stage.visuals",
    steps: ["storyboards", "video_prompts", "thumbnail_prompts", "seedance_clips"],
    estimatedSeconds: 370,
  },
  {
    id: "export",
    label: "stage.export",
    steps: ["tts_audio", "thumbnail_images", "assemble_final", "audit"],
    estimatedSeconds: 320,
  },
];

/** Return average duration (seconds) for a given step from historical runs.
 *  Looks at the same step name across all steps that have duration_ms recorded.
 *  Falls back to stage-level average, then to hard-coded estimate.
 */
function getAverageDurationForStepType(
  stepName: string,
  steps: Record<string, any>,
): number | null {
  // Same step name, done, with recorded duration
  const sameStep = Object.entries(steps).filter(
    ([name, data]) =>
      name === stepName &&
      data?.status === "done" &&
      data?.duration_ms &&
      data.duration_ms > 0,
  );
  if (sameStep.length > 0) {
    const avg =
      sameStep.reduce((sum, [, d]) => sum + (d.duration_ms as number), 0) /
      sameStep.length;
    return avg / 1000;
  }

  // Find the stage this step belongs to
  const stage = STAGES.find((s) => s.steps.includes(stepName));
  if (!stage) return null;

  // Average of all done steps in the same stage that have duration_ms
  const stageDoneWithDuration = stage.steps
    .map((s) => steps[s])
    .filter((d) => d?.status === "done" && d?.duration_ms && d.duration_ms > 0);

  if (stageDoneWithDuration.length > 0) {
    const avg =
      stageDoneWithDuration.reduce((sum, d) => sum + d.duration_ms, 0) /
      stageDoneWithDuration.length;
    return avg / 1000;
  }

  return null;
}

function getStageProgress(stage: (typeof STAGES)[0], steps: Record<string, any>): number {
  const total = stage.steps.length;
  const done = stage.steps.filter((s) => steps[s]?.status === "done").length;
  return total === 0 ? 0 : Math.round((done / total) * 100);
}

function getStageStatus(stageId: string, steps: Record<string, any>, t: (key: string) => string): string {
  if (stageId === "writing") {
    if (steps.scripts?.status === "done") return t("stage.substatus.scriptComplete");
    if (steps.strategy?.status === "done") return t("stage.substatus.generatingScripts");
    return t("stage.substatus.analyzing");
  }
  if (stageId === "visuals") {
    if (steps.seedance_clips?.status === "done") return t("stage.substatus.clipsComplete");
    if (steps.video_prompts?.status === "done") return t("stage.substatus.creatingClips");
    return t("stage.substatus.designingStoryboard");
  }
  if (stageId === "export") {
    if (steps.audit?.status === "done") return t("stage.substatus.exportComplete");
    if (steps.assemble_final?.status === "done") return t("stage.substatus.runningAudit");
    return t("stage.substatus.assembling");
  }
  return "";
}

export default function StageProgress({ label, onComplete }: Props) {
  const { t } = useI18n();
  const [steps, setSteps] = useState<Record<string, any>>({});
  const [elapsed, setElapsed] = useState(0);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const completedRef = useRef(false);
  const failureCountRef = useRef(0);
  const POLL_FAILURE_THRESHOLD = 15;
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

  // Polling for state
  const poll = useCallback(async () => {
    try {
      const data = await fetchS1State(label);
      failureCountRef.current = 0; // Reset on success
      const newSteps = data?.steps || data?.state?.steps || {};
      setSteps(newSteps);

      const allDone = STAGES.every((stage) =>
        stage.steps.every((s) => {
          const status = newSteps[s]?.status;
          return status === "done";
        })
      );
      if (allDone && !completedRef.current) {
        completedRef.current = true;
        if (pollingRef.current) clearInterval(pollingRef.current);
        if (timerRef.current) clearInterval(timerRef.current);
        // Brief delay so the user sees the completion animation
        setTimeout(() => onComplete(data), 1500);
      }
    } catch {
      failureCountRef.current += 1;
      if (failureCountRef.current >= POLL_FAILURE_THRESHOLD) {
        console.error("StageProgress: polling failed after %d consecutive attempts", failureCountRef.current);
        // Don't stop polling — just log. The user sees elapsed time continuing.
      }
    }
  }, [label, onComplete]);

  useEffect(() => {
    pollingRef.current = setInterval(poll, 2000);
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, [poll]);

  const formatTime = (seconds: number): string => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  };

  const estimatedRemaining = (() => {
    if (allComplete) return 0;
    if (elapsed < 5) return null;

    let completedActual = 0;   // sum of recorded duration_ms for done steps
    let completedFallback = 0; // sum of estimatedSeconds for done steps without duration_ms
    let remainingEstimate = 0; // sum of estimates for pending/in-progress steps

    for (const stage of STAGES) {
      for (const st of stage.steps) {
        const stepData = steps[st];
        const isDone = stepData?.status === "done";
        const hasDuration = stepData?.duration_ms && stepData.duration_ms > 0;

        if (isDone) {
          if (hasDuration) {
            completedActual += stepData.duration_ms / 1000;
          } else {
            completedFallback += stage.estimatedSeconds / stage.steps.length;
          }
        } else {
          // For pending/in-progress steps, prefer average of same-type completed steps
          const sameTypeAvg = getAverageDurationForStepType(st, steps);
          remainingEstimate += sameTypeAvg || (stage.estimatedSeconds / stage.steps.length);
        }
      }
    }

    const completedTotal = completedActual + completedFallback;
    if (completedTotal <= 0) return null;

    // Pace calibration: actual elapsed vs (actual + estimated fallback for completed work)
    const pace = elapsed / completedTotal;
    const remaining = Math.round(remainingEstimate * pace);
    return Math.max(remaining, 0);
  })();

  // Total pipeline progress
  const totalSteps = STAGES.reduce((sum, s) => sum + s.steps.length, 0);
  const totalDone = STAGES.reduce((sum, s) => sum + s.steps.filter((st) => steps[st]?.status === "done").length, 0);
  const totalProgress = totalSteps === 0 ? 0 : Math.round((totalDone / totalSteps) * 100);

  return (
    <div className="apple-card p-6 space-y-5 relative overflow-hidden">
      {/* Full completion celebration razzle */}
      {allComplete && (
        <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
          <div className="absolute inset-0 bg-gradient-to-b from-[#7CB342]/5 via-transparent to-transparent animate-pulse" />
        </div>
      )}

      {/* Header — warm to cool temperature shift */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          {/* Ambient breathing dot */}
          <div className="relative w-3 h-3">
            <div
              className={`absolute inset-0 rounded-full transition-all duration-1000 ${
                allComplete
                  ? "bg-[#7CB342]"
                  : "bg-[#7CB342]"
              }`}
              style={{
                animation: allComplete
                  ? "stagePulse 0.8s ease-in-out 3"
                  : stageStates[activeStageIdx]?.anyStarted
                  ? "stageBreathe 2s ease-in-out infinite"
                  : "none",
              }}
            />
            {stageStates[activeStageIdx]?.anyStarted && !allComplete && (
              <div
                className="absolute inset-0 rounded-full bg-[#7CB342]/30"
                style={{ animation: "stageRipple 2s ease-out infinite" }}
              />
            )}
          </div>
          <div>
            <h3 className="text-sm font-semibold text-[#1d1d1f] leading-tight">
              {allComplete ? t("pipeline.allDone") : t("mode.smartCreate")}
            </h3>
            {!allComplete && (
              <p className="text-[10px] text-[#aeaeb2] leading-tight">
                {totalProgress}% &middot; {stageStates.filter((s) => s.allDone).length}/{STAGES.length} {t("step.items")}
              </p>
            )}
          </div>
        </div>
        {/* Elapsed counter */}
        <div className="flex items-center gap-2">
          <span className="text-[10px] uppercase tracking-widest text-[#aeaeb2] font-medium">
            {allComplete ? t("stage.export") : t("stage.elapsed")}
          </span>
          <span className="text-sm font-mono font-semibold text-[#1d1d1f] tabular-nums">
            {formatTime(elapsed)}
          </span>
        </div>
      </div>

      {/* Animated pipeline — fills as stages complete */}
      <div className="relative">
        {/* Pipeline track */}
        <div className="absolute left-[11px] top-3 bottom-3 w-1 rounded-full bg-[#e8e8ed]" />

        {/* Pipeline fill — animated gradient */}
        <div
          className="absolute left-[11px] top-3 w-1 rounded-full transition-all duration-1000 ease-out"
          style={{
            height: `${allComplete ? 100 : Math.min((totalDone / totalSteps) * 100, 100)}%`,
            background: "linear-gradient(to bottom, #7CB342, #5B8DEF)",
            opacity: totalDone > 0 ? 1 : 0,
          }}
        />

        <div className="space-y-5">
          {STAGES.map((stage, idx) => {
            const isActive = idx === activeStageIdx && !allComplete;
            const isComplete = stageStates[idx].allDone;
            const isWaiting = !stageStates[idx].anyStarted && !isComplete;
            const progress = stageStates[idx].progress;
            const statusText = getStageStatus(stage.id, steps, t);
            const celebrating = celebrations[idx];

            return (
              <div key={stage.id} className="relative pl-10">
                {/* Pipeline node — the dot on the line */}
                <div className="absolute left-[8px] top-2 z-10">
                  <div
                    className={`w-[7px] h-[7px] rounded-full transition-all duration-500 ${
                      isComplete
                        ? "bg-[#7CB342] shadow-[0_0_6px_rgba(124,179,66,0.4)]"
                        : isActive
                        ? "bg-[#7CB342]"
                        : "bg-[#e8e8ed]"
                    } ${
                      celebrating ? "animate-[stagePop_0.5s_ease-out]" : ""
                    }`}
                  />
                  {/* Celebration ripple */}
                  {celebrating && (
                    <div
                      className="absolute inset-0 rounded-full bg-[#7CB342]/40"
                      style={{
                        animation: "stageRipple 0.8s ease-out forwards",
                        transform: "scale(1)",
                      }}
                    />
                  )}
                </div>

                {/* Stage content */}
                <div
                  className={`transition-opacity duration-500 ${
                    isWaiting ? "opacity-40" : "opacity-100"
                  }`}
                >
                  {/* Stage header */}
                  <div className="flex items-center gap-2 mb-1.5">
                    {/* Stage-specific icon as metaphor */}
                    <StageIcon
                      stageId={stage.id}
                      active={isActive}
                      complete={isComplete}
                      celebrating={celebrating}
                    />
                    <span
                      className={`text-[13px] font-medium transition-colors duration-500 ${
                        isComplete
                          ? "text-[#1d1d1f]"
                          : isActive
                          ? "text-[#7CB342]"
                          : "text-[#aeaeb2]"
                      }`}
                    >
                      {t(stage.label)}
                    </span>
                    {isComplete && (
                      <svg
                        width="14"
                        height="14"
                        viewBox="0 0 14 14"
                        fill="none"
                        className="shrink-0"
                        style={{ animation: celebrating ? "stagePop 0.5s ease-out" : "none" }}
                      >
                        <path
                          d="M3 7.5L5.5 10L11 4"
                          stroke="#7CB342"
                          strokeWidth="1.5"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                    )}
                  </div>

                  {/* Stage body */}
                  <div className="ml-0 space-y-1.5">
                    {/* Completed */}
                    {isComplete && !isActive && (
                      <p className="text-[11px] text-[#86868b] italic">
                        {stage.steps.filter((s) => steps[s]?.status === "done").length} {t("step.items")} &middot;{" "}
                        {t("stage.completed")}
                      </p>
                    )}

                    {/* Active — breathing progress */}
                    {isActive && (
                      <>
                        <p className="text-[11px] text-[#86868b]">{statusText}</p>
                        <div className="h-1.5 w-full bg-[#f5f5f7] rounded-full overflow-hidden">
                          <div
                            className="h-full rounded-full transition-all duration-1000 ease-out"
                            style={{
                              width: `${progress}%`,
                              background:
                                stage.id === "writing"
                                  ? "linear-gradient(to right, #C8A96E, #7CB342)"
                                  : stage.id === "visuals"
                                  ? "linear-gradient(to right, #7CB342, #5B8DEF)"
                                  : "linear-gradient(to right, #5B8DEF, #7C3AED)",
                            }}
                          />
                        </div>
                        <div className="flex justify-between text-[10px]">
                          <span className="text-[#aeaeb2]">
                            {stage.steps.filter((s) => steps[s]?.status === "done").length}/{stage.steps.length}
                          </span>
                          <span
                            className="font-mono font-medium"
                            style={{
                              color:
                                stage.id === "writing"
                                  ? "#C8A96E"
                                  : stage.id === "visuals"
                                  ? "#5B8DEF"
                                  : "#7C3AED",
                            }}
                          >
                            {progress}%
                          </span>
                        </div>
                      </>
                    )}

                    {/* Waiting */}
                    {isWaiting && (
                      <p className="text-[11px] text-[#aeaeb2] italic">{t("stage.waiting")}</p>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between pt-3 border-t border-[#e8e8ed]">
        <span className="text-[10px] text-[#aeaeb2]">
          {t("stage.elapsed")}: {formatTime(elapsed)}
        </span>
        {estimatedRemaining !== null && !allComplete && (
          <span className="text-[10px] text-[#86868b]">
            {t("stage.estimatedTime")}: ~{formatTime(estimatedRemaining)}
          </span>
        )}
        {allComplete && (
          <span className="text-[10px] font-medium text-[#7CB342]">
            {t("pipeline.allDone")} &middot; {formatTime(elapsed)}
          </span>
        )}
      </div>

      {/* Inline CSS keyframes — scoped to this component via unique names */}
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
}: {
  stageId: string;
  active: boolean;
  complete: boolean;
  celebrating: boolean;
}) {
  const color = complete ? "#7CB342" : active ? "#7CB342" : "#aeaeb2";
  const size = 16;

  // Writing stage: quill pen — bobs when active
  if (stageId === "writing") {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="shrink-0"
        style={{
          animation: active ? "stageBreathe 2s ease-in-out infinite" : celebrating ? "stagePop 0.5s ease-out" : "none",
        }}
      >
        {/* Quill */}
        <path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
        <path d="M15 5c1.5 1.5 3 3 4 4" opacity="0.5" />
      </svg>
    );
  }

  // Visuals stage: camera aperture — pulses when generating
  if (stageId === "visuals") {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="shrink-0"
        style={{
          animation: active ? "stageBreathRotate 3s ease-in-out infinite" : celebrating ? "stagePop 0.5s ease-out" : "none",
        }}
      >
        {/* Camera body */}
        <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
        {/* Lens */}
        <circle cx="12" cy="13" r="4" />
        {/* Aperture blades (shown when active) */}
        {active && (
          <>
            <path d="M12 9v8" opacity="0.3" />
            <path d="M9 12h6" opacity="0.3" />
          </>
        )}
      </svg>
    );
  }

  // Export stage: film strip — frames slide when active
  if (stageId === "export") {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="shrink-0"
        style={{
          animation: active ? "stageBreathe 2s ease-in-out infinite" : celebrating ? "stagePop 0.5s ease-out" : "none",
        }}
      >
        {/* Film strip body */}
        <rect x="2" y="4" width="20" height="16" rx="2" />
        {/* Perforations */}
        <line x1="2" y1="8" x2="22" y2="8" opacity="0.4" />
        <line x1="2" y1="16" x2="22" y2="16" opacity="0.4" />
        {/* Film frames */}
        <rect x="4" y="9" width="3" height="6" rx="0.5" opacity={complete ? "0.8" : "0.3"} />
        <rect x="8" y="9" width="3" height="6" rx="0.5" opacity={active || complete ? "0.8" : "0.2"} />
        <rect x="12" y="9" width="3" height="6" rx="0.5" opacity={complete ? "0.8" : "0.2"} />
      </svg>
    );
  }

  return null;
}
