"use client";

import { useState, useCallback } from "react";
import { getMediaUrl } from "./api";
import { useI18n } from "@/i18n/I18nProvider";
import { errorMessage } from "@/lib/errors";
import { getSoftDegradedSummary } from "@/lib/softDegraded";

type UnknownRecord = Record<string, unknown>;

type WorkflowConfig = UnknownRecord & {
  product_catalog?: {
    name?: string;
    products?: Array<{ name?: string }>;
  };
  brand_guidelines?: { brand_name?: string };
  target_platforms?: string[];
  video_duration?: number;
  content_scenario?: string;
};

type StepState = UnknownRecord & {
  status?: string;
  output?: unknown;
  edited_output?: unknown;
  duration_ms?: number;
};

type WorkflowState = UnknownRecord & {
  steps?: Record<string, StepState>;
  meta?: {
    step_order?: string[];
    step_durations?: Record<string, string>;
  };
  errors?: string[];
  soft_degraded_reasons?: Array<{ step?: string; reason?: string; detail?: string }>;
};

type StepItem = UnknownRecord & {
  id?: string;
  platform?: string;
  hook_type?: string;
  topic?: string;
  product_name?: string;
  brand_name?: string;
  description?: string;
  key_message?: string;
  target_audience?: string;
  script_id?: string;
  prompt?: string;
  text?: string;
  scene_title?: string;
  visual_description?: string;
  shot_type?: string;
};

type ScriptSegment = UnknownRecord & {
  segment_type?: string;
  start_time?: number;
  end_time?: number;
  voiceover?: string;
  description?: string;
  visual_description?: string;
  text_overlay?: string;
};

type ScriptItem = StepItem & {
  segments?: ScriptSegment[];
};

type StoryboardItem = StepItem & {
  shots?: unknown[];
  total_duration?: number;
};

type ClipDetail = {
  duration?: number;
  is_stub?: boolean;
  is_filler?: boolean;
  continuity_frame?: unknown;
  verification?: { all_ok?: boolean };
};

function asRecord(value: unknown): UnknownRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? value as UnknownRecord : {};
}

function asArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? value as T[] : [];
}

interface Props {
  config: unknown;
  label: string;
  state: unknown;
  onStateChange: (newState: WorkflowState) => void;
  onComplete: (finalState: WorkflowState) => void;
  onReset: () => void;
  loading: boolean;
  setLoading: (v: boolean) => void;
  setLoadingText: (v: string) => void;
}

const _FALLBACK_STEP_ORDER = [
  "strategy",
  "scripts",
  "compliance",
  "storyboards",
  "keyframe_images",
  "video_prompts",
  "thumbnail_prompts",
  "seedance_clips",
  "tts_audio",
  "thumbnail_images",
  "assemble_final",
  "audit",
];

const _FALLBACK_STEP_DURATIONS: Record<string, string> = {
  strategy: "~5s",
  scripts: "~5s",
  compliance: "~2s",
  storyboards: "~4s",
  keyframe_images: "~5-60s",
  video_prompts: "~3s",
  thumbnail_prompts: "~3s",
  seedance_clips: "~6min",
  tts_audio: "~3min",
  thumbnail_images: "~2min",
  assemble_final: "~15s",
  audit: "~5s",
};

export default function VideoWorkflow({
  config: rawConfig,
  label,
  state: rawState,
  onStateChange,
  onComplete,
  onReset,
  loading,
  setLoading,
  setLoadingText,
}: Props) {
  const { t } = useI18n();
  const [viewingStep, setViewingStep] = useState<string | null>(null);
  const [editingStep, setEditingStep] = useState<string | null>(null);
  const [runningStep, setRunningStep] = useState<string | null>(null);

  const config = asRecord(rawConfig) as WorkflowConfig;
  const state = asRecord(rawState) as WorkflowState;
  const steps = state?.steps || {};
  const stepOrder: string[] = state?.meta?.step_order || _FALLBACK_STEP_ORDER;
  const stepDurations: Record<string, string> = state?.meta?.step_durations || _FALLBACK_STEP_DURATIONS;
  const errors = asArray<string>(state.errors);
  const softDegradedReasons: Array<{ step?: string; reason?: string; detail?: string }> = state?.soft_degraded_reasons || [];
  const softDegradedSummary = softDegradedReasons[0];
  const softDegradedDisplay = getSoftDegradedSummary(softDegradedSummary, t);

  /** Format a duration from milliseconds to human-readable text.
   *  e.g. 5000 → "~5s", 180000 → "~3min"
   */
  const formatDuration = (ms: number): string => {
    if (ms < 1000) return "~0s";
    if (ms < 60000) return `~${Math.round(ms / 1000)}s`;
    return `~${Math.round(ms / 60000)}min`;
  };

  /** Return display label for a step's duration.
   *  Prefers recorded duration_ms from state, falls back to hard-coded estimate.
   */
  const getStepDurationLabel = (stepName: string): string => {
    const dur = steps[stepName]?.duration_ms;
    if (typeof dur === "number" && dur > 0) {
      return formatDuration(dur);
    }
    return stepDurations[stepName] || "";
  };

  const getCurrentStep = (): string | null => {
    for (const step of stepOrder) {
      if (!steps[step] || steps[step].status !== "done") {
        return step;
      }
    }
    return null;
  };

  const currentStep = getCurrentStep();
  const allDone = currentStep === null;

  const refreshState = useCallback(async () => {
    const { fetchS1State } = await import("./api");
    const fresh = await fetchS1State(label);
    onStateChange(asRecord(fresh.state || fresh) as WorkflowState);
  }, [label, onStateChange]);

  const handleRunStep = async (stepName: string) => {
    setLoading(true);
    setLoadingText(t("editors.running") + `: ${t("wstep." + stepName)}...`);
    setRunningStep(stepName);
    try {
      const { runS1Step } = await import("./api");
      const result = await runS1Step(label, stepName);
      const newState = asRecord(result?.state || result) as WorkflowState;
      onStateChange(newState);
      setViewingStep(stepName);
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      const msg = errorMessage(e);
      try { await refreshState(); } catch { /* best-effort reload */ }
      showToast(t("toast.stepExecFailed") + `: ${msg}`, "error");
    } finally {
      setLoading(false);
      setRunningStep(null);
      setLoadingText(t("app.loading"));
    }
  };

  const handleRegenerate = async (stepName: string) => {
    setLoading(true);
    setLoadingText(t("editors.regenerating") + `: ${t("wstep." + stepName)}...`);
    setRunningStep(stepName);
    try {
      const { regenerateS1Step } = await import("./api");
      const result = await regenerateS1Step(label, stepName);
      const newState = asRecord(result?.state || result) as WorkflowState;
      onStateChange(newState);
      setViewingStep(stepName);
      setEditingStep(null);
    } catch (e: unknown) {
      const msg = errorMessage(e);
      if (e instanceof DOMException && e.name === "AbortError") return;
      try { await refreshState(); } catch { /* best-effort reload */ }
      showToast(t("toast.regenerateFailed") + `: ${msg}`, "error");
    } finally {
      setLoading(false);
      setRunningStep(null);
      setLoadingText(t("app.loading"));
    }
  };

  const handleSaveEdit = async (stepName: string, newOutput: unknown) => {
    setLoading(true);
    setLoadingText(t("editors.saving"));
    try {
      const { updateS1State } = await import("./api");
      const updatedSteps = { ...steps };
      updatedSteps[stepName] = {
        ...updatedSteps[stepName],
        output: newOutput,
        edited: true,
        edited_output: newOutput,
      };
      await updateS1State(label, { steps: updatedSteps });
      onStateChange({ ...state, steps: updatedSteps });
      setEditingStep(null);
      showToast(t("toast.saveSuccess"), "success");
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      try { await refreshState(); } catch { /* best-effort reload */ }
      showToast(t("toast.saveFailed") + `: ${errorMessage(e)}`, "error");
    } finally {
      setLoading(false);
      setLoadingText(t("app.loading"));
    }
  };

  const handleResume = async () => {
    setLoading(true);
    setLoadingText(t("editors.resuming"));
    try {
      const { resumeS1 } = await import("./api");
      const result = await resumeS1(label);
      const finalState = result?.state || result;
      onStateChange(finalState);
      onComplete(finalState);
    } catch (e: unknown) {
      const msg = errorMessage(e);
      if (e instanceof DOMException && e.name === "AbortError") return;
      try { await refreshState(); } catch { /* best-effort reload */ }
      showToast(t("toast.resumeFailed") + `: ${msg}`, "error");
    } finally {
      setLoading(false);
      setLoadingText(t("app.loading"));
    }
  };

  const [toast, setToast] = useState<{ message: string; type: "success" | "error" } | null>(null);
  const showToast = (message: string, type: "success" | "error") => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  };

  const productName = config?.product_catalog?.products?.[0]?.name
    || config?.product_catalog?.name
    || t("common.unknownProduct");
  const brandName = config?.brand_guidelines?.brand_name || "";
  const platforms = config?.target_platforms || [];
  const duration = config?.video_duration || 10;
  const scenarioLabel = config?.content_scenario === "product_direct" ? t("workflow.productDirect") : t("workflow.liveShoot");

  return (
    <div className="space-y-3 animate-slide-up">
      {toast && (
        <div className={`apple-toast apple-toast-${toast.type}`}>
          <div className="flex items-center gap-2">{toast.message}</div>
        </div>
      )}

      {/* Config Summary Card */}
      <div className="apple-card p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-[rgba(215,92,112,0.10)] flex items-center justify-center">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--fortune-red)" strokeWidth="2">
                <rect x="3" y="3" width="18" height="18" rx="2" />
                <line x1="9" y1="9" x2="15" y2="9" />
                <line x1="9" y1="12" x2="15" y2="12" />
                <line x1="9" y1="15" x2="11" y2="15" />
              </svg>
            </div>
            <div>
              <h2 className="text-sm font-semibold text-[var(--text-h1)]">{t("workflow.title")}</h2>
              <p className="text-[12px] text-[var(--text-body)]">Label: {label}</p>
            </div>
          </div>
          <span className={`text-[12px] font-semibold px-2 py-0.5 rounded-full ${allDone ? "bg-[rgba(215,92,112,0.10)] text-[var(--fortune-red)]" : "bg-[rgba(255,149,0,0.10)] text-[var(--gold-foil)]"}`}>
            {allDone ? t("wstatus.allDone") : t("wstatus.running")}
          </span>
        </div>

        <div className="grid grid-cols-4 gap-2">
          <div className="bg-[var(--bg-panel)] rounded-lg p-2">
            <p className="text-[12px] text-[var(--text-body)] uppercase">{t("workflow.product")}</p>
            <p className="text-xs font-medium text-[var(--text-h1)] truncate">{productName}</p>
          </div>
          <div className="bg-[var(--bg-panel)] rounded-lg p-2">
            <p className="text-[12px] text-[var(--text-body)] uppercase">{t("workflow.brand")}</p>
            <p className="text-xs font-medium text-[var(--text-h1)]">{brandName || "-"}</p>
          </div>
          <div className="bg-[var(--bg-panel)] rounded-lg p-2">
            <p className="text-[12px] text-[var(--text-body)] uppercase">{t("workflow.duration")}</p>
            <p className="text-xs font-medium text-[var(--text-h1)]">{duration}s</p>
          </div>
          <div className="bg-[var(--bg-panel)] rounded-lg p-2">
            <p className="text-[12px] text-[var(--text-body)] uppercase">{t("workflow.scenario")}</p>
            <p className="text-xs font-medium text-[var(--text-h1)]">{scenarioLabel}</p>
          </div>
        </div>

        {platforms.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {platforms.map((p: string) => (
              <span key={p} className="text-[12px] px-2 py-0.5 rounded-full bg-[rgba(215,92,112,0.10)] text-[var(--fortune-red)] border border-[rgba(215,92,112,0.15)]">
                {t("platform." + p)}
              </span>
            ))}
          </div>
        )}

        {softDegradedReasons.length > 0 && (
          <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-2.5">
            <p className="text-[12px] font-medium text-amber-800">
              {t("degraded.softTitle")}
              {softDegradedDisplay.stepLabel ? ` · ${softDegradedDisplay.stepLabel}` : ""}
              {softDegradedDisplay.reasonLabel ? ` · ${softDegradedDisplay.reasonLabel}` : ""}
            </p>
            {softDegradedDisplay.detail ? (
              <p className="mt-1 text-[12px] text-amber-700">{softDegradedDisplay.detail}</p>
            ) : null}
          </div>
        )}
      </div>

      {/* Steps Timeline */}
      <div className="apple-card p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-xs font-semibold text-[var(--text-h1)]">{t("workflow.timeline")}</h3>
          <span className="text-[12px] text-[var(--text-body)]">
            {stepOrder.filter((s) => steps[s]?.status === "done").length} / {stepOrder.length} {t("workflow.completed")}
          </span>
        </div>

        <div className="space-y-1">
          {stepOrder.map((stepName, index) => {
            const stepData = steps[stepName] || { status: "pending" };
            const isDone = stepData.status === "done";
            const isCurrent = stepName === currentStep;
            const isRunning = runningStep === stepName;
            const hasError = stepData.status === "error" || errors.some((e) => e.includes(stepName));
            const isEdited = stepData.edited === true;

            return (
              <div key={stepName} className="space-y-1">
                <div
                  className={`flex items-center gap-2 p-2.5 rounded-lg border transition-all ${
                    hasError
                      ? "bg-[rgba(196,91,80,0.08)] border-[var(--crimson-mist)] ring-1 ring-[rgba(196,91,80,0.10)]"
                      : isDone
                      ? isEdited
                        ? "bg-[rgba(215,92,112,0.05)] border-[rgba(215,92,112,0.30)] ring-1 ring-[rgba(215,92,112,0.10)]"
                        : "bg-[var(--bg-panel)] border-[var(--border-default)]"
                      : isCurrent
                      ? "bg-[var(--bg-card)] border-[var(--fortune-red)] ring-1 ring-[rgba(215,92,112,0.20)]"
                      : "bg-[var(--bg-card)] border-[var(--border-default)] opacity-50"
                  }`}
                >
                  <span className={`text-[12px] font-mono w-5 text-center ${isDone ? "text-[var(--fortune-red)]" : isCurrent ? "text-[var(--gold-foil)]" : "text-[var(--text-muted)]"}`}>
                    {isDone ? (
                      <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                        <path d="M4 8.5L7 11.5L12 5" stroke="var(--fortune-red)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    ) : (
                      index + 1
                    )}
                  </span>

                  <div className={`w-2 h-2 rounded-full shrink-0 ${
                    hasError ? "bg-[var(--crimson-mist)]" : isDone ? "bg-[var(--fortune-red)]" : isCurrent ? "bg-[var(--gold-foil)] animate-pulse" : "bg-[var(--border-default)]"
                  }`} />

                  <span className={`text-xs font-medium flex-1 ${hasError ? "text-[var(--crimson-mist)]" : isDone ? "text-[var(--text-h1)]" : isCurrent ? "text-[var(--text-h1)]" : "text-[var(--text-muted)]"}`}>
                    {t("wstep." + stepName)}
                  </span>

                  {isEdited && (
                    <span className="text-[12px] px-1.5 py-0.5 rounded-full bg-[rgba(215,92,112,0.10)] text-[var(--fortune-red)] font-medium">{t("stepStatus.edited")}</span>
                  )}

                  <span className="text-[12px] text-[var(--text-muted)] hidden sm:inline">{getStepDurationLabel(stepName)}</span>

                  <span className={`text-[12px] font-medium ${hasError ? "text-[var(--crimson-mist)]" : isDone ? "text-[var(--fortune-red)]" : isCurrent ? "text-[var(--gold-foil)]" : "text-[var(--text-muted)]"}`}>
                    {hasError ? t("stepStatus.failed") : isDone ? t("stepStatus.completed") : isCurrent ? t("stepStatus.pending") : t("stepStatus.notStarted")}
                  </span>

                  {isDone && !isRunning && (
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => {
                          setViewingStep(viewingStep === stepName ? null : stepName);
                          setEditingStep(null);
                        }}
                        className="text-[12px] text-[var(--fortune-red)] hover:underline cursor-pointer px-1.5 py-0.5 rounded hover:bg-[rgba(215,92,112,0.05)]"
                      >
                        {viewingStep === stepName ? t("waction.hide") : t("waction.view")}
                      </button>
                      <button
                        onClick={() => {
                          setEditingStep(editingStep === stepName ? null : stepName);
                          setViewingStep(stepName);
                        }}
                        className="text-[12px] text-[var(--gold-foil)] hover:underline cursor-pointer px-1.5 py-0.5 rounded hover:bg-[rgba(255,149,0,0.05)]"
                      >
                        {editingStep === stepName ? t("waction.cancelEdit") : t("waction.edit")}
                      </button>
                      <button
                        onClick={() => handleRegenerate(stepName)}
                        disabled={loading}
                        className="text-[12px] text-[var(--text-body)] hover:text-[var(--text-h1)] cursor-pointer px-1.5 py-0.5 rounded hover:bg-[rgba(215,92,112,0.18)] disabled:opacity-50"
                      >
                        {t("waction.regenerate")}
                      </button>
                    </div>
                  )}

                  {isCurrent && (
                    <button
                      onClick={() => handleRunStep(stepName)}
                      disabled={loading}
                      className="apple-btn apple-btn-primary text-[12px] px-2.5 py-1 disabled:opacity-50"
                    >
                      {isRunning ? (
                        <span className="flex items-center gap-1">
                          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" className="animate-spin">
                            <circle cx="12" cy="12" r="10" stroke="rgba(255,255,255,0.3)" strokeWidth="3" />
                            <path d="M12 2a10 10 0 0 1 10 10" stroke="white" strokeWidth="3" strokeLinecap="round" />
                          </svg>
                          {t("waction.running")}
                        </span>
                      ) : (
                        t("waction.runStep")
                      )}
                    </button>
                  )}

                  {hasError && (
                    <button
                      onClick={() => handleRunStep(stepName)}
                      disabled={loading}
                      className="apple-btn text-[12px] px-2.5 py-1 bg-[var(--crimson-mist)] hover:bg-[var(--neon-red)] text-white disabled:opacity-50"
                    >
                      {t("waction.retry")}
                    </button>
                  )}
                </div>

                {/* Step Output / Edit Panel */}
                {viewingStep === stepName && isDone && (
                  <div className="ml-7 animate-slide-up">
                    {editingStep === stepName ? (
                      <StepEditor
                        stepName={stepName}
                        output={stepData.output}
                        onSave={(newOutput) => handleSaveEdit(stepName, newOutput)}
                        onCancel={() => setEditingStep(null)}
                      />
                    ) : (
                      <StepOutput stepName={stepName} output={stepData.output} />
                    )}
                  </div>
                )}

                {hasError && errors.filter((e) => e.includes(stepName)).map((err, i) => (
                  <div key={i} className="ml-7 p-2 bg-[rgba(196,91,80,0.08)] rounded-lg border border-[rgba(196,91,80,0.20)]">
                    <p className="text-[12px] text-[var(--crimson-mist)]">{err}</p>
                  </div>
                ))}
              </div>
            );
          })}
        </div>

        <div className="mt-4 pt-3 border-t border-[var(--border-default)] flex gap-2">
          {!allDone && (
            <button
              onClick={handleResume}
              disabled={loading}
              className="apple-btn apple-btn-primary flex-1 py-2 text-sm disabled:opacity-50"
            >
              {t("waction.resumeAll")}
            </button>
          )}
          {allDone && (
            <button
              onClick={() => onComplete(state)}
              className="apple-btn apple-btn-primary flex-1 py-2 text-sm"
            >
              {t("waction.viewResult")}
            </button>
          )}
          <button
            onClick={onReset}
            disabled={loading}
            className="apple-btn py-2 text-sm px-4 bg-[var(--bg-panel)] text-[var(--text-body)] hover:text-[var(--text-h1)] hover:bg-[rgba(215,92,112,0.18)] disabled:opacity-50"
          >
            {t("waction.abandon")}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ── Step Editor ── */

function StepEditor({ stepName, output, onSave, onCancel }: {
  stepName: string;
  output: unknown;
  onSave: (v: unknown) => void;
  onCancel: () => void;
}) {
  const { t: te } = useI18n();
  const [draft, setDraft] = useState(() => JSON.parse(JSON.stringify(output)));

  const handleSave = () => {
    onSave(draft);
  };

  if (stepName === "strategy" || stepName === "compliance") {
    const draftRecord = asRecord(draft);
    const briefs = Array.isArray(draft) ? asArray<StepItem>(draft) : asArray<StepItem>(draftRecord.briefs);
    return (
      <div className="space-y-2 p-2">
        <p className="text-[12px] text-[var(--text-body)] mb-1">{te("editors.briefs")}</p>
        {briefs.map((b, i) => (
          <div key={i} className="apple-card p-3 bg-[var(--bg-card)] space-y-2">
            <div className="flex items-center gap-2">
              <span className="text-[12px] font-mono text-[var(--text-muted)]">#{i + 1}</span>
              <span className="text-[12px] font-semibold text-[var(--fortune-red)]">{b.id || `BRIEF-${String(i + 1).padStart(3, "0")}`}</span>
            </div>
            <div>
              <label className="block text-[12px] font-medium text-[var(--text-body)] mb-0.5">{te("editors.topic")}</label>
              <input
                type="text"
                value={b.topic || ""}
                onChange={(e) => {
                  const newBriefs = [...briefs];
                  newBriefs[i] = { ...b, topic: e.target.value };
                  setDraft({ ...asRecord(draft), briefs: newBriefs });
                }}
                className="apple-input text-xs w-full"
              />
            </div>
            <div>
              <label className="block text-[12px] font-medium text-[var(--text-body)] mb-0.5">{te("editors.target_audience")}</label>
              <input
                type="text"
                value={b.target_audience || ""}
                onChange={(e) => {
                  const newBriefs = [...briefs];
                  newBriefs[i] = { ...b, target_audience: e.target.value };
                  setDraft({ ...asRecord(draft), briefs: newBriefs });
                }}
                className="apple-input text-xs w-full"
              />
            </div>
            <div>
              <label className="block text-[12px] font-medium text-[var(--text-body)] mb-0.5">{te("editors.key_message")}</label>
              <textarea
                value={b.key_message || ""}
                onChange={(e) => {
                  const newBriefs = [...briefs];
                  newBriefs[i] = { ...b, key_message: e.target.value };
                  setDraft({ ...asRecord(draft), briefs: newBriefs });
                }}
                className="apple-input text-xs w-full resize-none"
                rows={2}
              />
            </div>
            <div>
              <label className="block text-[12px] font-medium text-[var(--text-body)] mb-0.5">{te("editors.hook_type")}</label>
              <input
                type="text"
                value={b.hook_type || ""}
                onChange={(e) => {
                  const newBriefs = [...briefs];
                  newBriefs[i] = { ...b, hook_type: e.target.value };
                  setDraft({ ...asRecord(draft), briefs: newBriefs });
                }}
                className="apple-input text-xs w-full"
              />
            </div>
          </div>
        ))}
        <div className="flex gap-2 pt-1">
          <button onClick={handleSave} className="apple-btn apple-btn-primary text-xs px-3 py-1.5">{te("editors.save")}</button>
          <button onClick={onCancel} className="apple-btn text-xs px-3 py-1.5 bg-[var(--bg-panel)] text-[var(--text-body)]">{te("editors.cancel")}</button>
        </div>
      </div>
    );
  }

  if (stepName === "scripts") {
    const draftRecord = asRecord(draft);
    const scripts = Array.isArray(draft) ? asArray<ScriptItem>(draft) : asArray<ScriptItem>(draftRecord.scripts);
    return (
      <div className="space-y-2 p-2">
        <p className="text-[12px] text-[var(--text-body)] mb-1">{te("editors.scripts")}</p>
        {scripts.map((s, si) => (
          <div key={si} className="apple-card p-3 bg-[var(--bg-card)] space-y-2">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[12px] font-mono text-[var(--text-muted)]">{s.id || `S${si + 1}`}</span>
              <span className="text-xs font-semibold text-[var(--text-h1)]">{s.product_name || s.brand_name || "Script"}</span>
            </div>
            {(s.segments || []).map((seg, j) => (
              <div key={j} className="pl-3 border-l-2 border-[var(--border-default)] space-y-1.5 py-1">
                <div className="flex items-center gap-2">
                  <span className="text-[12px] font-semibold text-[var(--fortune-red)] uppercase">{seg.segment_type}</span>
                  <span className="text-[12px] text-[var(--text-muted)] font-mono">{seg.start_time ?? 0}s — {seg.end_time ?? 0}s</span>
                </div>
                <div>
                  <label className="block text-[12px] font-medium text-[var(--text-body)] mb-0.5">{te("editors.voiceover")}</label>
                  <textarea
                    value={seg.voiceover || ""}
                    onChange={(e) => {
                      const newScripts = [...scripts];
                      const newSegs = [...(s.segments || [])];
                      newSegs[j] = { ...seg, voiceover: e.target.value };
                      newScripts[si] = { ...s, segments: newSegs };
                      setDraft({ ...asRecord(draft), scripts: newScripts });
                    }}
                    className="apple-input text-xs w-full resize-none"
                    rows={2}
                  />
                </div>
                <div>
                  <label className="block text-[12px] font-medium text-[var(--text-body)] mb-0.5">{te("editors.visual_desc")}</label>
                  <textarea
                    value={seg.visual_description || ""}
                    onChange={(e) => {
                      const newScripts = [...scripts];
                      const newSegs = [...(s.segments || [])];
                      newSegs[j] = { ...seg, visual_description: e.target.value };
                      newScripts[si] = { ...s, segments: newSegs };
                      setDraft({ ...asRecord(draft), scripts: newScripts });
                    }}
                    className="apple-input text-xs w-full resize-none"
                    rows={2}
                  />
                </div>
                <div className="mt-2">
                  <label className="text-[12px] font-medium text-[var(--text-body)] mb-1 block">{te("editors.text_overlay")}</label>
                  <input
                    type="text"
                    value={seg.text_overlay || ''}
                    onChange={(e) => {
                      const newScripts = [...scripts];
                      const newSegs = [...(s.segments || [])];
                      newSegs[j] = { ...seg, text_overlay: e.target.value };
                      newScripts[si] = { ...s, segments: newSegs };
                      setDraft({ ...asRecord(draft), scripts: newScripts });
                    }}
                    placeholder={te("editors.text_overlay_placeholder")}
                    className="w-full bg-[var(--bg-card)] border border-[var(--border-default)] rounded-lg px-3 py-1.5 text-[13px] text-[var(--text-h1)] focus:outline-none focus:border-[var(--fortune-red)] transition-colors"
                  />
                </div>
              </div>
            ))}
          </div>
        ))}
        <div className="flex gap-2 pt-1">
          <button onClick={handleSave} className="apple-btn apple-btn-primary text-xs px-3 py-1.5">{te("editors.save")}</button>
          <button onClick={onCancel} className="apple-btn text-xs px-3 py-1.5 bg-[var(--bg-panel)] text-[var(--text-body)]">{te("editors.cancel")}</button>
        </div>
      </div>
    );
  }

  if (stepName === "storyboards") {
    const draftRecord = asRecord(draft);
    const boards = Array.isArray(draft) ? asArray<StoryboardItem>(draft) : asArray<StoryboardItem>(draftRecord.storyboards);
    return (
      <div className="space-y-2 p-2">
        <p className="text-[12px] text-[var(--text-body)] mb-1">{te("editors.storyboards")}</p>
        {boards.map((b, i) => (
          <div key={i} className="apple-card p-3 bg-[var(--bg-card)] space-y-2">
            <div className="flex items-center gap-2">
              <span className="text-[12px] font-mono text-[var(--text-muted)]">#{i + 1}</span>
              <input
                type="text"
                value={b.scene_title || ""}
                onChange={(e) => {
                  const newBoards = [...boards];
                  newBoards[i] = { ...b, scene_title: e.target.value };
                  setDraft({ ...asRecord(draft), storyboards: newBoards });
                }}
                className="apple-input text-xs flex-1"
                placeholder={te("editors.scene_title_placeholder")}
              />
            </div>
            <div>
              <label className="block text-[12px] font-medium text-[var(--text-body)] mb-0.5">{te("editors.visual_desc")}</label>
              <textarea
                value={b.visual_description || ""}
                onChange={(e) => {
                  const newBoards = [...boards];
                  newBoards[i] = { ...b, visual_description: e.target.value };
                  setDraft({ ...asRecord(draft), storyboards: newBoards });
                }}
                className="apple-input text-xs w-full resize-none"
                rows={3}
              />
            </div>
            <div>
              <label className="block text-[12px] font-medium text-[var(--text-body)] mb-0.5">{te("editors.shot_type")}</label>
              <input
                type="text"
                value={b.shot_type || ""}
                onChange={(e) => {
                  const newBoards = [...boards];
                  newBoards[i] = { ...b, shot_type: e.target.value };
                  setDraft({ ...asRecord(draft), storyboards: newBoards });
                }}
                className="apple-input text-xs w-full"
                placeholder={te("editors.shot_type_placeholder")}
              />
            </div>
          </div>
        ))}
        <div className="flex gap-2 pt-1">
          <button onClick={handleSave} className="apple-btn apple-btn-primary text-xs px-3 py-1.5">{te("editors.save")}</button>
          <button onClick={onCancel} className="apple-btn text-xs px-3 py-1.5 bg-[var(--bg-panel)] text-[var(--text-body)]">{te("editors.cancel")}</button>
        </div>
      </div>
    );
  }

  if (stepName === "video_prompts" || stepName === "thumbnail_prompts") {
    const draftRecord = asRecord(draft);
    const prompts = Array.isArray(draft) ? asArray<StepItem | string>(draft) : asArray<StepItem | string>(draftRecord.prompts);
    return (
      <div className="space-y-2 p-2">
        <p className="text-[12px] text-[var(--text-body)] mb-1">{te("editors.prompts")}</p>
        {prompts.map((p, i) => (
          <div key={i} className="apple-card p-3 bg-[var(--bg-card)] space-y-2">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[12px] font-mono text-[var(--text-muted)]">#{i + 1}</span>
              {typeof p !== "string" && p.platform && (
                <span className="text-[12px] font-semibold px-2 py-0.5 rounded-full bg-[rgba(215,92,112,0.10)] text-[var(--fortune-red)]">
                  {te("platform." + p.platform)}
                </span>
              )}
            </div>
            <textarea
              value={typeof p === "string" ? p : p.text || p.prompt || ""}
              onChange={(e) => {
                const newPrompts = [...prompts];
                if (typeof p === "string") {
                  newPrompts[i] = e.target.value;
                } else {
                  newPrompts[i] = { ...p, text: e.target.value, prompt: e.target.value };
                }
                  setDraft({ ...asRecord(draft), prompts: newPrompts });
              }}
              className="apple-input text-xs w-full resize-none"
              rows={4}
            />
          </div>
        ))}
        <div className="flex gap-2 pt-1">
          <button onClick={handleSave} className="apple-btn apple-btn-primary text-xs px-3 py-1.5">{te("editors.save")}</button>
          <button onClick={onCancel} className="apple-btn text-xs px-3 py-1.5 bg-[var(--bg-panel)] text-[var(--text-body)]">{te("editors.cancel")}</button>
        </div>
      </div>
    );
  }

  // Fallback: generic JSON editor for any other step
  return (
    <div className="space-y-2 p-2">
      <p className="text-[12px] text-[var(--text-body)] mb-1">{te("editors.json")}</p>
      <textarea
        value={JSON.stringify(draft, null, 2)}
        onChange={(e) => {
          try {
            setDraft(JSON.parse(e.target.value));
          } catch { /* invalid JSON — user is still typing */ }
        }}
        className="apple-input text-xs w-full font-mono resize-none"
        rows={10}
      />
      <div className="flex gap-2 pt-1">
        <button onClick={handleSave} className="apple-btn apple-btn-primary text-xs px-3 py-1.5">{te("editors.save")}</button>
        <button onClick={onCancel} className="apple-btn text-xs px-3 py-1.5 bg-[var(--bg-panel)] text-[var(--text-body)]">{te("editors.cancel")}</button>
      </div>
    </div>
  );
}

/* ── Step Output (read-only) ── */

function StepOutput({ stepName, output }: { stepName: string; output: unknown }) {
  const { t: to } = useI18n();
  if (!output) return <p className="text-xs text-[var(--text-muted)] p-2">{to("step.noOutput")}</p>;
  const outputRecord = asRecord(output);

  if (stepName === "strategy" || stepName === "compliance") {
    const briefs = Array.isArray(output) ? asArray<StepItem>(output) : asArray<StepItem>(outputRecord.briefs);
    if (briefs.length === 0) return <p className="text-xs text-[var(--text-muted)] p-2">{to("step.noStrategy")}</p>;
    return (
      <div className="space-y-2 p-2">
        {briefs.map((b, i) => (
          <div key={i} className="apple-card p-3 bg-[var(--bg-card)]">
            <div className="flex items-start gap-2 mb-1">
              {b.platform && (
                <span className="text-[12px] font-semibold px-2 py-0.5 rounded-full bg-[rgba(215,92,112,0.10)] text-[var(--fortune-red)] shrink-0">
                  {to("platform." + b.platform)}
                </span>
              )}
              {b.hook_type && (
                <span className="text-[12px] font-medium px-2 py-0.5 rounded-full bg-[rgba(89,88,94,0.10)] text-[var(--text-body)]">
                  {b.hook_type}
                </span>
              )}
            </div>
            <h4 className="text-sm font-semibold text-[var(--text-h1)] mb-1">{b.topic || b.product_name || b.brand_name || "Brief"}</h4>
            {b.target_audience && <p className="text-[12px] text-[var(--text-muted)] mb-1">{to("editors.target_audience")}:{b.target_audience}</p>}
            {b.key_message && <p className="text-xs text-[var(--text-body)] leading-relaxed">{b.key_message}</p>}
            {b.description && <p className="text-xs text-[var(--text-body)] leading-relaxed mt-1">{b.description}</p>}
          </div>
        ))}
      </div>
    );
  }

  if (stepName === "scripts") {
    const scripts = Array.isArray(output) ? asArray<ScriptItem>(output) : asArray<ScriptItem>(outputRecord.scripts);
    if (scripts.length === 0) return <p className="text-xs text-[var(--text-muted)] p-2">{to("step.noScript")}</p>;
    return (
      <div className="space-y-2 p-2">
        {scripts.map((s, i) => (
          <details key={i} className="apple-card overflow-hidden">
            <summary className="p-3 cursor-pointer flex items-center gap-2 list-none">
              <span className="text-[12px] font-mono text-[var(--text-muted)]">{s.id || `S${i + 1}`}</span>
              <span className="text-sm font-medium text-[var(--text-h1)] flex-1">{s.product_name || s.brand_name || "Script"}</span>
              <span className="text-[12px] text-[var(--text-muted)]">{(s.segments || []).length}{to("step.segments")}</span>
            </summary>
            <div className="px-3 pb-3 space-y-2 border-t border-[var(--border-default)] pt-2">
              {(s.segments || []).map((seg, j) => (
                <div key={j} className="pl-3 border-l-2 border-[var(--border-default)]">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-[12px] font-semibold text-[var(--fortune-red)] uppercase">{seg.segment_type}</span>
                    <span className="text-[12px] text-[var(--text-muted)] font-mono">
                      {seg.start_time ?? 0}s — {seg.end_time ?? 0}s
                    </span>
                  </div>
                  <p className="text-xs text-[var(--text-h1)]">{seg.voiceover}</p>
                  {seg.visual_description && <p className="text-[12px] text-[var(--text-body)] mt-1 italic">{seg.visual_description}</p>}
                  {seg.text_overlay && (
                    <p className="text-[12px] text-[var(--fortune-red)] font-medium mt-1 bg-[rgba(110,150,110,0.12)] px-2 py-0.5 rounded-md inline-block">
                      {seg.text_overlay}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </details>
        ))}
      </div>
    );
  }

  if (stepName === "storyboards") {
    const boards = Array.isArray(output) ? asArray<StoryboardItem>(output) : asArray<StoryboardItem>(outputRecord.storyboards);
    if (boards.length === 0) return <p className="text-xs text-[var(--text-muted)] p-2">{to("step.noStoryboard")}</p>;
    return (
      <div className="space-y-2 p-2">
        {boards.map((b, i) => (
          <div key={i} className="apple-card p-3 bg-[var(--bg-card)]">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[12px] font-mono text-[var(--text-muted)]">#{i + 1}</span>
              <span className="text-xs font-semibold text-[var(--text-h1)]">{b.scene_title || "Scene"}</span>
            </div>
            {b.visual_description && <p className="text-[12px] text-[var(--text-body)] italic">{b.visual_description}</p>}
            {b.shot_type && <p className="text-[12px] text-[var(--text-muted)] mt-1">{to("editors.shot_type")}:{b.shot_type}</p>}
          </div>
        ))}
      </div>
    );
  }

  if (stepName === "seedance_clips") {
    // New format: {clip_paths, clip_details, total_duration, target_duration}
    // Old format: string[]
    const isNewFormat = !Array.isArray(output) && Array.isArray(outputRecord.clip_paths);
    const rawUrls = isNewFormat ? asArray<string>(outputRecord.clip_paths) : (Array.isArray(output) ? asArray<string>(output) : asArray<string>(outputRecord.urls));
    const details = isNewFormat ? asArray<ClipDetail>(outputRecord.clip_details) : [];
    const totalDur = isNewFormat && typeof outputRecord.total_duration === "number" ? outputRecord.total_duration : 0;
    const targetDur = isNewFormat && typeof outputRecord.target_duration === "number" ? outputRecord.target_duration : 0;
    const urls = rawUrls.map((url: string) => getMediaUrl(url));
    if (urls.length === 0) return <p className="text-xs text-[var(--text-muted)] p-2">{to("step.noMedia")}</p>;
    return (
      <div className="space-y-2 p-2">
        {isNewFormat && targetDur > 0 && (
          <div className="flex items-center gap-2 text-[12px]">
            <span className="text-[var(--text-body)]">
              {to("step.totalDuration")}: {totalDur.toFixed(1)}s / {targetDur}s
            </span>
            <span className={`px-1.5 py-0.5 rounded-full font-medium ${totalDur >= targetDur * 0.8 ? "bg-[rgba(215,92,112,0.10)] text-[var(--fortune-red)]" : "bg-[rgba(255,149,0,0.10)] text-[var(--gold-foil)]"}`}>
              {totalDur >= targetDur * 0.8 ? to("step.durationOk") : to("step.durationShort")}
            </span>
          </div>
        )}
        <div className="grid grid-cols-2 gap-2">
          {urls.map((url: string, i: number) => {
            const meta = details[i] || {};
            const duration = meta.duration;
            const isStub = meta.is_stub;
            const isFiller = meta.is_filler;
            const hasContinuity = Boolean(meta.continuity_frame);
            const ver = meta.verification || {};
            const verOk = ver.all_ok !== false;
            return (
              <div key={i} className={`apple-card overflow-hidden ${isStub ? "border-[rgba(255,149,0,0.30)]" : ""} ${isFiller ? "border-[rgba(122,150,187,0.30)]" : ""}`}>
                <video src={url} controls className="w-full h-32 object-cover" />
                <div className="p-2 space-y-1">
                  <div className="flex items-center gap-1 flex-wrap">
                    <span className="text-[12px] font-mono text-[var(--text-muted)]">#{i + 1}</span>
                    {typeof duration === "number" && duration > 0 && (
                      <span className="text-[12px] text-[var(--text-body)]">{duration.toFixed(1)}s</span>
                    )}
                    {isStub && (
                      <span className="text-[12px] px-1.5 py-0.5 rounded-full bg-[rgba(255,149,0,0.10)] text-[var(--gold-foil)] font-medium">
                        {to("step.stub")}
                      </span>
                    )}
                    {isFiller && (
                      <span className="text-[12px] px-1.5 py-0.5 rounded-full bg-[rgba(122,150,187,0.10)] text-[var(--cinema-azure)] font-medium">
                        {to("step.filler")}
                      </span>
                    )}
                    {hasContinuity && (
                      <span className="text-[12px] px-1.5 py-0.5 rounded-full bg-[rgba(215,92,112,0.10)] text-[var(--fortune-red)] font-medium">
                        {to("step.continuity")}
                      </span>
                    )}
                    {!verOk && (
                      <span className="text-[12px] px-1.5 py-0.5 rounded-full bg-[rgba(196,91,80,0.10)] text-[var(--crimson-mist)] font-medium">
                        {to("step.verifyFail")}
                      </span>
                    )}
                  </div>
                  <p className="text-[12px] text-[var(--text-muted)] truncate">{url}</p>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  if (stepName === "thumbnail_images") {
    const rawUrls = Array.isArray(output) ? asArray<string>(output) : asArray<string>(outputRecord.urls);
    const urls = rawUrls.map((url: string) => getMediaUrl(url));
    if (urls.length === 0) return <p className="text-xs text-[var(--text-muted)] p-2">{to("step.noMedia")}</p>;
    return (
      <div className="grid grid-cols-2 gap-2 p-2">
        {urls.map((url: string, i: number) => (
          <div key={i} className="apple-card overflow-hidden">
            {/* Generated thumbnails are backend-runtime paths; native img avoids Next image loader allowlist drift. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={url} alt={`Asset ${i + 1}`} className="w-full h-32 object-cover" />
            <p className="text-[12px] text-[var(--text-muted)] p-2 truncate">{url}</p>
          </div>
        ))}
      </div>
    );
  }

  if (stepName === "tts_audio") {
    // Format: {"audio_paths": [...], "lyrics_paths": [...]}
    const rawUrls = Array.isArray(output)
      ? asArray<string>(output)
      : asArray<string>(outputRecord.audio_paths || outputRecord.urls);
    const urls = rawUrls.map((url: string) => getMediaUrl(url));
    if (urls.length === 0) return <p className="text-xs text-[var(--text-muted)] p-2">{to("step.noMedia")}</p>;
    return (
      <div className="space-y-2 p-2">
        {urls.map((url: string, i: number) => (
          <div key={i} className="apple-card p-3 bg-[var(--bg-card)]">
            <audio src={url} controls preload="metadata" className="w-full" />
          </div>
        ))}
      </div>
    );
  }

  if (stepName === "assemble_final") {
    const rawUrl = typeof output === "string" ? output : typeof outputRecord.final_video_url === "string" ? outputRecord.final_video_url : "";
    const finalUrl = getMediaUrl(rawUrl);
    if (!finalUrl) return <p className="text-xs text-[var(--text-muted)] p-2">{to("step.noData")}</p>;
    return (
      <div className="p-2">
        <div className="apple-card overflow-hidden">
          <video src={finalUrl} controls className="w-full" />
          <div className="p-2">
            <a href={finalUrl} target="_blank" rel="noopener noreferrer" className="text-[12px] text-[var(--fortune-red)] hover:underline">
              {to("result.downloadVideo")}
            </a>
          </div>
        </div>
      </div>
    );
  }

  return (
    <pre className="text-[12px] font-mono text-[var(--text-body)] bg-[var(--bg-card)] p-3 rounded-lg overflow-auto max-h-[300px] whitespace-pre-wrap break-all">
      {JSON.stringify(output, null, 2)}
    </pre>
  );
}
